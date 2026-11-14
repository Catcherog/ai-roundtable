using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        string state = Environment.GetEnvironmentVariable("AI_ROUNDTABLE_HOME")
            ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), ".ai-roundtable");
        try
        {
            state = Path.GetFullPath(state);
            string key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(state.ToUpperInvariant())));
            using var single = new Mutex(true, @"Local\AI-Roundtable-" + key, out bool first);
            if (!first) { MessageBox.Show("AI 圆桌已经打开。请切换到现有窗口。", "AI Roundtable"); return; }
            Directory.CreateDirectory(state);
            Application.Run(new RoundtableWindow(state));
        }
        catch (Exception ex) { MessageBox.Show(ex.Message, "AI Roundtable", MessageBoxButtons.OK, MessageBoxIcon.Error); }
    }
}

internal sealed class RoundtableWindow : Form
{
    private readonly WebView2 view = new() { Dock = DockStyle.Fill };
    private readonly Label loading = new() { Dock = DockStyle.Fill, Text = "正在打开 AI 圆桌…", TextAlign = ContentAlignment.MiddleCenter };
    private readonly HttpClient client = new(new HttpClientHandler { UseProxy = false }) { Timeout = TimeSpan.FromSeconds(3) };
    private readonly string state;
    private readonly string token = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
    private readonly string bootId = Convert.ToHexString(RandomNumberGenerator.GetBytes(16));
    private readonly ProcessJob job = new();
    private Process? backend;
    private Uri? origin;
    private bool closeChecked, checkingClose, ready;

    public RoundtableWindow(string state)
    {
        this.state = state;
        Text = "AI 圆桌 · AI Roundtable";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Width = 1360; Height = 900; MinimumSize = new Size(920, 620);
        StartPosition = FormStartPosition.CenterScreen;
        Controls.Add(view); Controls.Add(loading);
        Shown += async (_, _) => await StartAsync();
        FormClosing += ClosingRequested;
        FormClosed += (_, _) => { job.Dispose(); backend?.Dispose(); client.Dispose(); };
    }

    private async Task StartAsync()
    {
        try
        {
            string root = AppContext.BaseDirectory;
            string workspace = Path.Combine(state, "workspace");
            Directory.CreateDirectory(workspace);
            var start = new ProcessStartInfo(Path.Combine(root, "runtime", "python.exe"))
            {
                UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = root,
                RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8, StandardErrorEncoding = Encoding.UTF8
            };
            foreach (string arg in new[] { "-I", "-X", "utf8", "-u", Path.Combine(root, "app", "backend", "server.py"),
                     "--host", "127.0.0.1", "--port", "0", "--workspace", workspace, "--notify-parent", "--wait-for-parent" })
                start.ArgumentList.Add(arg);
            start.Environment["AI_ROUNDTABLE_HOME"] = state;
            start.Environment["AI_ROUNDTABLE_BOOT_TOKEN"] = token;
            start.Environment["AI_ROUNDTABLE_BOOT_ID"] = bootId;
            start.Environment.Remove("AI_ROUNDTABLE_BOOTSTRAP_CODE");
            backend = Process.Start(start) ?? throw new IOException("无法启动本地服务。");
            var listening = new TaskCompletionSource<int>(TaskCreationOptions.RunContinuationsAsynchronously);
            backend.EnableRaisingEvents = true;
            backend.Exited += (_, _) => listening.TrySetException(new IOException("本地服务已退出，请重新打开应用。"));
            backend.OutputDataReceived += (_, e) => {
                const string prefix = "ROUNDTABLE_PORT=";
                if (e.Data?.StartsWith(prefix, StringComparison.Ordinal) == true && int.TryParse(e.Data[prefix.Length..], out int port))
                    listening.TrySetResult(port);
            };
            var tail = new Queue<string>();
            backend.ErrorDataReceived += (_, e) => { if (e.Data != null) lock (tail) { tail.Enqueue(e.Data); if (tail.Count > 8) tail.Dequeue(); } };
            backend.BeginOutputReadLine(); backend.BeginErrorReadLine();
            try { job.Attach(backend); await backend.StandardInput.WriteLineAsync("START"); }
            finally { backend.StandardInput.Close(); }
            int port;
            try { port = await listening.Task.WaitAsync(TimeSpan.FromSeconds(45)); }
            catch (Exception ex) { string detail; lock (tail) detail = string.Join(Environment.NewLine, tail); throw new IOException(ex.Message + Environment.NewLine + detail, ex); }
            origin = new Uri($"http://127.0.0.1:{port}/");
            client.DefaultRequestHeaders.Add("X-Roundtable-Token", token);
            using var status = await client.GetFromJsonAsync<JsonDocument>(new Uri(origin, "api/status"));
            if (status?.RootElement.GetProperty("boot_id").GetString() != bootId) throw new IOException("本地服务身份验证失败。");
            var env = await CoreWebView2Environment.CreateAsync(null, Path.Combine(state, "WebView2"));
            await view.EnsureCoreWebView2Async(env);
            var core = view.CoreWebView2;
            core.Settings.AreHostObjectsAllowed = false;
            core.NavigationStarting += (_, e) => { if (!Trusted(e.Uri)) e.Cancel = true; };
            core.FrameNavigationStarting += (_, e) => e.Cancel = true;
            core.NewWindowRequested += (_, e) => { e.Handled = true; };
            core.PermissionRequested += (_, e) => e.State = CoreWebView2PermissionState.Deny;
            core.DownloadStarting += (_, e) => {
                var dialog = new SaveFileDialog { FileName = Path.GetFileName(e.ResultFilePath), Filter = "Markdown (*.md)|*.md", AddExtension = true };
                using (dialog) { if (dialog.ShowDialog(this) == DialogResult.OK) { e.ResultFilePath = dialog.FileName; e.Handled = true; } else e.Cancel = true; }
            };
            core.WebMessageReceived += NativeRequest;
            // Only main frames at this process's loopback origin get the two native operations.
            string originJson = JsonSerializer.Serialize(origin.GetLeftPart(UriPartial.Authority));
            await core.AddScriptToExecuteOnDocumentCreatedAsync("""
                (() => {
                  if (window !== window.top || location.origin !== ORIGIN) return;
                  const pending = new Map();
                  chrome.webview.addEventListener('message', ({data}) => {
                    const take = pending.get(data.id);
                    if (take) { pending.delete(data.id); take(data.value); }
                  });
                  window.roundtableDesktop = {postMessage({action}) {
                    const id = crypto.randomUUID();
                    return new Promise(resolve => { pending.set(id,resolve); chrome.webview.postMessage({id,action}); });
                  }};
                })();
                """.Replace("ORIGIN", originJson));
            core.Navigate(origin.AbsoluteUri);
            loading.Visible = false; ready = true;
        }
        catch (WebView2RuntimeNotFoundException) { Fatal("请安装 Microsoft Edge WebView2 Evergreen Runtime，然后重新打开 AI 圆桌。\nhttps://developer.microsoft.com/microsoft-edge/webview2/"); }
        catch (Exception ex) { Fatal("AI 圆桌启动失败。\n" + ex.Message); }
    }

    private bool Trusted(string url) => origin != null && Uri.TryCreate(url, UriKind.Absolute, out var u)
        && u.Scheme == origin.Scheme && u.Host == origin.Host && u.Port == origin.Port && string.IsNullOrEmpty(u.UserInfo);

    private void NativeRequest(object? sender, CoreWebView2WebMessageReceivedEventArgs e)
    {
        if (!Trusted(e.Source)) return;
        using var payload = JsonDocument.Parse(e.WebMessageAsJson);
        var msg = payload.RootElement;
        if (msg.ValueKind != JsonValueKind.Object || !msg.TryGetProperty("id", out var id) || id.ValueKind != JsonValueKind.String ||
            !msg.TryGetProperty("action", out var cmd) || cmd.ValueKind != JsonValueKind.String) return;
        object value;
        switch (cmd.GetString())
        {
            case "getBootAuth": value = new { token, bootId, port = origin!.Port }; break;
            case "pickFolder":
                using (var folder = new FolderBrowserDialog { Description = "选择项目目录", UseDescriptionForTitle = true })
                    value = folder.ShowDialog(this) == DialogResult.OK ? folder.SelectedPath : "";
                break;
            default: return;
        }
        if (Trusted(view.Source.AbsoluteUri)) view.CoreWebView2.PostWebMessageAsJson(JsonSerializer.Serialize(new { id = id.GetString(), value }));
    }

    private void Fatal(string message)
    {
        closeChecked = true;
        MessageBox.Show(this, message, "AI Roundtable", MessageBoxButtons.OK, MessageBoxIcon.Error);
        Close();
    }

    private async void ClosingRequested(object? sender, FormClosingEventArgs e)
    {
        if (closeChecked || !ready || origin == null) return;
        e.Cancel = true;
        if (checkingClose) return;
        checkingClose = true;
        bool? busy = null;
        try {
            using var result = await client.GetFromJsonAsync<JsonDocument>(new Uri(origin, "api/status"));
            busy = result?.RootElement.GetProperty("system").GetProperty("has_busy_session").GetBoolean();
        } catch (HttpRequestException) {} catch (TaskCanceledException) {}
        checkingClose = false;
        if (busy != false && MessageBox.Show(this, busy == true ? "会议正在运行。结束任务并退出？" : "暂时无法确认会议状态。仍然退出？",
                "AI Roundtable", MessageBoxButtons.YesNo, MessageBoxIcon.Question, MessageBoxDefaultButton.Button2) != DialogResult.Yes) return;
        closeChecked = true; BeginInvoke(new Action(Close));
    }
}
