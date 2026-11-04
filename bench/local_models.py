"""Verified downloads and sequential CUDA serving. No PyTorch installation required."""
from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
LLAMA = ROOT / "tools" / "llama-cuda"
SERVER = LLAMA / "llama-server.exe"
MODELS = ROOT / "models"
RELEASE = "b11981"
ASSETS = ["llama-b11981-bin-win-cuda-12.4-x64.zip", "cudart-llama-bin-win-cuda-12.4-x64.zip"]
SPECS = {
    "guiowl-1.5-2b": ("mradermacher/GUI-Owl-1.5-2B-Instruct-GGUF", "GUI-Owl-1.5-2B-Instruct", "Q4_K_M"),
    "uivenus-1.5-2b": ("mradermacher/UI-Venus-1.5-2B-GGUF", "UI-Venus-1.5-2B", "Q4_K_M"),
    "holo2-4b": ("mradermacher/Holo2-4B-GGUF", "Holo2-4B", "Q4_K_M"),
    "mai-ui-2b": ("mradermacher/MAI-UI-2B-GGUF", "MAI-UI-2B", "Q4_K_M"),
    "guiowl-1.5-4b": ("mradermacher/GUI-Owl-1.5-4B-Instruct-GGUF", "GUI-Owl-1.5-4B-Instruct", "Q4_K_M"),
}

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4*1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def fetch(url, dest, size, digest=None):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size == size and (not digest or sha256(dest) == digest):
        print(f"cached {dest.name}", flush=True)
        return dest
    part = dest.with_suffix(dest.suffix+".part")
    for attempt in range(5):
        try:
            offset = part.stat().st_size if part.exists() else 0
            if offset >= size:
                offset = 0
            with httpx.stream("GET",url,headers={"Range":f"bytes={offset}-"} if offset else {},
                              follow_redirects=True,timeout=120) as r:
                r.raise_for_status()
                if r.status_code != 206:
                    offset = 0
                with part.open("ab" if offset else "wb") as f:
                    for chunk in r.iter_bytes(1024*1024):
                        f.write(chunk)
            if part.stat().st_size != size:
                raise IOError(f"Incomplete download: {part.stat().st_size}/{size}")
            if digest and sha256(part) != digest:
                part.unlink()
                raise IOError("SHA256 mismatch")
            part.replace(dest)
            print(f"downloaded {dest.name} ({size/1e6:.0f} MB)",flush=True)
            return dest
        except (httpx.HTTPError,OSError) as e:
            print(f"attempt {attempt+1}/5 {dest.name}: {e}",flush=True)
            if attempt == 4:
                raise
            time.sleep(min(2**attempt,8))

def ensure_llama():
    marker = LLAMA/"verified-release.json"
    if SERVER.exists() and marker.exists():
        return
    r = httpx.get(f"https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{RELEASE}",timeout=60)
    r.raise_for_status()
    assets = {a["name"]:a for a in r.json()["assets"]}
    verified = []
    for name in ASSETS:
        a = assets[name]
        digest = (a.get("digest") or "").removeprefix("sha256:") or None
        path = fetch(a["browser_download_url"],LLAMA/name,a["size"],digest)
        with zipfile.ZipFile(path) as z:
            if any(not (LLAMA/m.filename).resolve().is_relative_to(LLAMA.resolve()) for m in z.infolist()):
                raise ValueError("Unsafe archive member")
            if z.testzip():
                raise ValueError("Corrupt runtime archive")
            z.extractall(LLAMA)
        verified.append({"name":name,"sha256":sha256(path)})
    marker.write_text(json.dumps({"release":RELEASE,"assets":verified},indent=2))

def download(name):
    repo,stem,quant = SPECS[name]
    r = httpx.get(f"https://huggingface.co/api/models/{repo}?blobs=true",timeout=60)
    r.raise_for_status()
    data = r.json()
    files = {s["rfilename"]:s for s in data["siblings"]}
    paths = []
    for filename in [f"{stem}.{quant}.gguf",f"{stem}.mmproj-Q8_0.gguf"]:
        entry = files[filename]
        paths.append(fetch(f"https://huggingface.co/{repo}/resolve/{data['sha']}/{filename}",
                           MODELS/filename,entry["size"],entry["lfs"]["sha256"]))
    (MODELS/f"{name}.provenance.json").write_text(json.dumps({"repo":repo,"revision":data["sha"],
        "files":[{"name":p.name,"size":p.stat().st_size,"sha256":sha256(p)} for p in paths]},indent=2))
    return paths

def start_server(name, gguf, mmproj, port=8089, image_tokens=1024):
    with (MODELS/f"{name}.server.log").open("ab") as log:
        proc = subprocess.Popen([str(SERVER),"-m",str(gguf),"--mmproj",str(mmproj),"-ngl","99",
            "-c","8192","--host","127.0.0.1","--port",str(port),"--jinja","--reasoning-budget","0",
            "--parallel","1","--flash-attn","on","--image-max-tokens",str(image_tokens)],
            stdout=log,stderr=log,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    try:
        with httpx.Client(timeout=2) as c:
            for _ in range(150):
                if proc.poll() is not None:
                    raise RuntimeError(f"Server exited {proc.returncode}; see {name}.server.log")
                try:
                    if c.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                        return proc
                except httpx.HTTPError:
                    pass
                time.sleep(1)
        raise TimeoutError("Server startup exceeded 150s")
    except BaseException:
        proc.terminate()
        proc.wait(timeout=15)
        raise

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("names",nargs="*")
    p.add_argument("--download-only",action="store_true")
    p.add_argument("--serve",action="store_true")
    p.add_argument("--image-tokens",type=int,default=1024)
    p.add_argument("--max-side",type=int,default=1280)
    p.add_argument("--port",type=int,default=8089)
    args = p.parse_args()
    names = args.names or ["guiowl-1.5-2b","uivenus-1.5-2b"]
    if any(n not in SPECS for n in names) or (args.serve and len(names) != 1):
        p.error("Supply known model names; --serve requires exactly one")
    with ThreadPoolExecutor(max_workers=2) as pool:
        runtime = pool.submit(ensure_llama)
        downloads = {n:pool.submit(download,n) for n in names}
        runtime.result()
        for name in names:
            gguf,mmproj = downloads[name].result()
            if args.download_only:
                continue
            proc = start_server(name,gguf,mmproj,args.port,args.image_tokens)
            try:
                if args.serve:
                    print(f"READY {name} pid={proc.pid} port={args.port}",flush=True)
                    proc.wait()
                else:
                    from bakeoff import run
                    r = run(name,1000,True,f"http://127.0.0.1:{args.port}",max_side=args.max_side,
                        out=ROOT/"bench"/"runs"/f"{name}-{args.max_side}-{args.image_tokens}.json")
                    print(json.dumps({k:v for k,v in r.items() if k != "cases"},indent=2),flush=True)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=15)

if __name__ == "__main__":
    main()
