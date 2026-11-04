// Disposable WinForms benchmark. The localhost endpoints are evaluator-only:
// GET /state reads ground truth; POST /reset?scenario=N resets this fixture.
// They are not a model observation surface and affect no other application.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class Program
{
    [DllImport("user32.dll")] private static extern bool SetProcessDPIAware();
    [STAThread] private static void Main()
    {
        SetProcessDPIAware();
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        Application.Run(new Fixture());
    }
}

internal sealed class Fixture : Form
{
    private readonly List<Dictionary<string, object>> events = new List<Dictionary<string, object>>();
    private readonly JavaScriptSerializer json = new JavaScriptSerializer();
    private TcpListener listener;
    private int scenario;
    private bool completed;
    private DateTime started;
    private TextBox project;
    private CheckBox previews;
    private Form modal;
    private Label status;

    public Fixture()
    {
        Text = "CU-S1 Native Benchmark";
        ClientSize = new Size(1000, 650);
        StartPosition = FormStartPosition.Manual;
        Location = new Point(160, 100);
        FormBorderStyle = FormBorderStyle.FixedSingle;
        MaximizeBox = false;
        Font = new Font("Segoe UI", 11);
        Shown += delegate { ResetFixture(0); StartServer(); };
        FormClosed += delegate { if (listener != null) listener.Stop(); };
    }

    private void Event(string name, object value)
    {
        events.Add(new Dictionary<string, object> {
            { "event", name }, { "value", value },
            { "time", DateTime.UtcNow.ToString("o") }
        });
    }

    private Label AddLabel(string text, int x, int y, int width, int height)
    {
        Label label = new Label { Text = text, Location = new Point(x, y), Size = new Size(width, height) };
        Controls.Add(label);
        return label;
    }

    private Button AddButton(Control parent, string text, int x, int y, int width, int height)
    {
        Button button = new Button { Text = text, AccessibleName = text, Location = new Point(x, y), Size = new Size(width, height) };
        parent.Controls.Add(button);
        return button;
    }

    private void ResetFixture(int id)
    {
        if (modal != null && !modal.IsDisposed) modal.Close();
        scenario = id;
        completed = false;
        events.Clear();
        started = DateTime.UtcNow;
        project = null;
        previews = null;
        Controls.Clear();
        AddLabel("Native task workspace", 35, 25, 650, 35).Font = new Font("Segoe UI", 18, FontStyle.Bold);
        status = AddLabel("Ready", 35, 595, 850, 30);
        if (id == 0) BuildForm();
        else if (id == 1) BuildRecords();
        else BuildReview();
        ActiveControl = null;
    }

    private void BuildForm()
    {
        AddLabel("Project code", 55, 115, 260, 27);
        project = new TextBox { Location = new Point(55, 148), Size = new Size(370, 34), AccessibleName = "Project code" };
        Controls.Add(project);
        project.Enter += delegate { Event("focus_project_code", null); };
        project.TextChanged += delegate { Event("project_code_changed", project.Text); };
        previews = new CheckBox { Text = "Enable previews", AccessibleName = "Enable previews", Location = new Point(55, 215), AutoSize = true };
        Controls.Add(previews);
        previews.CheckedChanged += delegate { Event("enable_previews", previews.Checked); };
        Button commit = AddButton(this, "Commit", 55, 290, 160, 45);
        commit.Click += delegate {
            completed = project.Text == "NOVA-82" && previews.Checked;
            Event("commit", completed);
            status.Text = completed ? "COMPLETE" : "Check the project code and preview setting";
        };
    }

    private void BuildRecords()
    {
        AddLabel("Records", 55, 90, 250, 30);
        AddLabel("Browse the records and approve the requested item.", 55, 125, 600, 30);
        Panel pane = new Panel { Location = new Point(55, 165), Size = new Size(700, 355), AutoScroll = true, BorderStyle = BorderStyle.FixedSingle, AccessibleName = "Records pane" };
        Controls.Add(pane);
        for (int n = 1; n <= 14; n++) {
            int number = n;
            Label label = new Label { Text = "Record R" + n.ToString("00"), Location = new Point(22, 15 + (n - 1) * 66), Size = new Size(310, 38) };
            pane.Controls.Add(label);
            Button button = AddButton(pane, "Approve R" + n.ToString("00"), 390, 12 + (n - 1) * 66, 190, 42);
            button.Click += delegate {
                completed = number == 14;
                Event("approve", "R" + number.ToString("00"));
                status.Text = completed ? "COMPLETE" : "Another record was selected";
            };
        }
        pane.Scroll += delegate { Event("records_scroll", pane.VerticalScroll.Value); };
    }

    private void BuildReview()
    {
        AddLabel("Review the preview before confirming.", 55, 115, 600, 30);
        Button review = AddButton(this, "Review details", 55, 165, 190, 45);
        review.Click += delegate {
            Event("review_details", null);
            using (Form dialog = new Form()) {
                modal = dialog;
                dialog.Text = "CU-S1 Review";
                dialog.StartPosition = FormStartPosition.CenterParent;
                dialog.ClientSize = new Size(500, 240);
                dialog.FormBorderStyle = FormBorderStyle.FixedDialog;
                dialog.MaximizeBox = false;
                dialog.MinimizeBox = false;
                dialog.Font = Font;
                CheckBox reviewed = new CheckBox { Text = "I reviewed the preview", AccessibleName = "I reviewed the preview", Location = new Point(35, 50), AutoSize = true };
                dialog.Controls.Add(reviewed);
                reviewed.CheckedChanged += delegate { Event("reviewed_preview", reviewed.Checked); };
                Button confirm = AddButton(dialog, "Confirm", 35, 120, 150, 45);
                confirm.Click += delegate {
                    completed = reviewed.Checked;
                    Event("confirm", completed);
                    status.Text = completed ? "COMPLETE" : "Review the preview before confirming";
                    if (completed) dialog.Close();
                };
                dialog.ShowDialog(this);
                modal = null;
            }
        };
    }

    private object State()
    {
        List<Dictionary<string, string>> steps = new List<Dictionary<string, string>>();
        if (scenario == 0) {
            steps.Add(new Dictionary<string, string> { { "do", "Click the Project code text field." } });
            steps.Add(new Dictionary<string, string> { { "do", "Type: NOVA-82" } });
            steps.Add(new Dictionary<string, string> { { "do", "Check Enable previews." } });
            steps.Add(new Dictionary<string, string> { { "do", "Click Commit." }, { "expect", "The status says COMPLETE." } });
        } else if (scenario == 1) {
            steps.Add(new Dictionary<string, string> { { "do", "Scroll down in the records pane until Approve R14 is visible." } });
            steps.Add(new Dictionary<string, string> { { "do", "Click Approve R14." }, { "expect", "The status says COMPLETE." } });
        } else {
            steps.Add(new Dictionary<string, string> { { "do", "Click Review details." } });
            steps.Add(new Dictionary<string, string> { { "do", "Check I reviewed the preview." } });
            steps.Add(new Dictionary<string, string> { { "do", "Click Confirm." }, { "expect", "The status says COMPLETE." } });
        }
        return new Dictionary<string, object> {
            { "scenario", scenario }, { "completed", completed }, { "events", events.ToArray() },
            { "steps", steps }, { "elapsed_ms", (DateTime.UtcNow - started).TotalMilliseconds },
            { "project_code", project == null ? null : project.Text },
            { "previews", previews == null ? (bool?)null : previews.Checked },
            { "modal_open", modal != null && !modal.IsDisposed }
        };
    }

    private void StartServer()
    {
        listener = new TcpListener(IPAddress.Loopback, 8095);
        listener.Start();
        Thread server = new Thread(ServerLoop);
        server.IsBackground = true;
        server.Start();
    }

    private void ServerLoop()
    {
        try {
            while (true) {
                TcpClient client = listener.AcceptTcpClient();
                ThreadPool.QueueUserWorkItem(HandleClient, client);
            }
        } catch (SocketException) { } catch (ObjectDisposedException) { }
    }

    private string OnUiThread(Func<string> operation)
    {
        string result = null;
        Exception failure = null;
        using (ManualResetEvent finished = new ManualResetEvent(false)) {
            BeginInvoke(new Action(delegate {
                try { result = operation(); }
                catch (Exception ex) { failure = ex; }
                finally { finished.Set(); }
            }));
            finished.WaitOne();
        }
        if (failure != null) throw new InvalidOperationException("UI operation failed", failure);
        return result;
    }

    private void HandleClient(object arg)
    {
        using (TcpClient client = (TcpClient)arg) {
            client.ReceiveTimeout = 5000;
            client.SendTimeout = 5000;
            try {
                NetworkStream stream = client.GetStream();
                StreamReader reader = new StreamReader(stream, Encoding.ASCII, false, 1024, true);
                string first = reader.ReadLine();
                if (String.IsNullOrEmpty(first)) return;
                string line;
                int headers = 0;
                while (!String.IsNullOrEmpty(line = reader.ReadLine())) {
                    if (++headers > 100 || line.Length > 8192) throw new InvalidDataException("Invalid headers");
                }
                string[] parts = first.Split(' ');
                if (parts.Length < 2) throw new InvalidDataException("Invalid request");
                Uri path = new Uri("http://localhost" + parts[1]);
                string response;
                string code = "200 OK";
                if (parts[0] == "GET" && path.AbsolutePath == "/state") {
                    response = OnUiThread(delegate { return json.Serialize(State()); });
                } else if (parts[0] == "POST" && path.AbsolutePath == "/reset") {
                    int id;
                    string query = path.Query;
                    if (!query.StartsWith("?scenario=") || !Int32.TryParse(query.Substring(10), out id) || id < 0 || id > 2) {
                        code = "400 Bad Request";
                        response = "{\"error\":\"scenario must be 0, 1, or 2\"}";
                    } else {
                        int selected = id;
                        response = OnUiThread(delegate { ResetFixture(selected); return json.Serialize(State()); });
                    }
                } else {
                    code = "404 Not Found";
                    response = "{\"error\":\"not found\"}";
                }
                byte[] body = Encoding.UTF8.GetBytes(response);
                byte[] header = Encoding.ASCII.GetBytes("HTTP/1.1 " + code + "\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: " + body.Length + "\r\nConnection: close\r\n\r\n");
                stream.Write(header, 0, header.Length);
                stream.Write(body, 0, body.Length);
            } catch (IOException) { } catch (SocketException) { } catch (ObjectDisposedException) { } catch (InvalidOperationException) { }
        }
    }
}
