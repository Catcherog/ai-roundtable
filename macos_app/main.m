// AI圆桌.app — 原生 macOS (Cocoa + WKWebView) 桌面端入口
// 支持：原生 NSOpenPanel 目录选择 Sheet、窗口关闭保留后台任务、Dock 图标唤醒、退出忙态确认与启动故障自愈重试
#import <Cocoa/Cocoa.h>
#import <WebKit/WebKit.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <signal.h>
#include <spawn.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static int findAvailablePort(int startPort, int maxPort) {
    for (int port = startPort; port <= maxPort; port++) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) continue;
        int opt = 1;
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        struct sockaddr_in addr;
        memset(&addr, 0, sizeof(addr));
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        addr.sin_addr.s_addr = inet_addr("127.0.0.1");
        int res = bind(sock, (struct sockaddr *)&addr, sizeof(addr));
        close(sock);
        if (res == 0) {
            return port;
        }
    }
    return startPort;
}

static NSURL *buildLocalURL(int port, NSString *path) {
    NSURLComponents *comp = [[NSURLComponents alloc] init];
    comp.scheme = @"http";
    comp.host = @"127.0.0.1";
    comp.port = @(port);
    comp.path = path;
    return comp.URL;
}

static NSString *escapeHtmlString(NSString *raw) {
    if (!raw) return @"";
    NSString *s = [raw stringByReplacingOccurrencesOfString:@"&" withString:@"&amp;"];
    s = [s stringByReplacingOccurrencesOfString:@"<" withString:@"&lt;"];
    s = [s stringByReplacingOccurrencesOfString:@">" withString:@"&gt;"];
    return s;
}

static NSString *escapeJsSingleQuoted(NSString *raw) {
    if (!raw) return @"";
    NSString *s = [raw stringByReplacingOccurrencesOfString:@"\\" withString:@"\\\\"];
    s = [s stringByReplacingOccurrencesOfString:@"'" withString:@"\\'"];
    s = [s stringByReplacingOccurrencesOfString:@"\n" withString:@" "];
    return s;
}

@interface AppDelegate : NSObject <NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandler, NSWindowDelegate>
@property (nonatomic, strong) NSWindow *window;
@property (nonatomic, strong) WKWebView *webView;
@property (nonatomic, assign) pid_t serverPid;
@property (nonatomic, assign) int serverPort;
@property (nonatomic, copy) NSString *bootLogPath;
@end

@implementation AppDelegate

- (void)setupMainMenu {
    NSMenu *menubar = [[NSMenu alloc] init];
    [NSApp setMainMenu:menubar];

    NSMenuItem *appMenuItem = [[NSMenuItem alloc] init];
    [menubar addItem:appMenuItem];
    NSMenu *appMenu = [[NSMenu alloc] initWithTitle:@"AI圆桌"];
    [appMenu addItemWithTitle:@"偏好设置…" action:@selector(openFrontendSettings:) keyEquivalent:@","];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"隐藏 AI圆桌" action:@selector(hide:) keyEquivalent:@"h"];
    [appMenu addItem:[NSMenuItem separatorItem]];
    [appMenu addItemWithTitle:@"退出 AI圆桌" action:@selector(terminate:) keyEquivalent:@"q"];
    [appMenuItem setSubmenu:appMenu];

    NSMenuItem *fileMenuItem = [[NSMenuItem alloc] init];
    [menubar addItem:fileMenuItem];
    NSMenu *fileMenu = [[NSMenu alloc] initWithTitle:@"会议"];
    [fileMenu addItemWithTitle:@"新建会议" action:@selector(createNewSession:) keyEquivalent:@"n"];
    [fileMenu addItemWithTitle:@"绑定本地项目目录…" action:@selector(openNativeFolderSheet:) keyEquivalent:@"o"];
    [fileMenuItem setSubmenu:fileMenu];

    NSMenuItem *editMenuItem = [[NSMenuItem alloc] init];
    [menubar addItem:editMenuItem];
    NSMenu *editMenu = [[NSMenu alloc] initWithTitle:@"编辑"];
    [editMenu addItemWithTitle:@"撤销" action:NSSelectorFromString(@"undo:") keyEquivalent:@"z"];
    [editMenu addItemWithTitle:@"重做" action:NSSelectorFromString(@"redo:") keyEquivalent:@"Z"];
    [editMenu addItem:[NSMenuItem separatorItem]];
    [editMenu addItemWithTitle:@"剪切" action:@selector(cut:) keyEquivalent:@"x"];
    [editMenu addItemWithTitle:@"拷贝" action:@selector(copy:) keyEquivalent:@"c"];
    [editMenu addItemWithTitle:@"粘贴" action:@selector(paste:) keyEquivalent:@"v"];
    [editMenu addItemWithTitle:@"全选" action:@selector(selectAll:) keyEquivalent:@"a"];
    [editMenuItem setSubmenu:editMenu];

    NSMenuItem *viewMenuItem = [[NSMenuItem alloc] init];
    [menubar addItem:viewMenuItem];
    NSMenu *viewMenu = [[NSMenu alloc] initWithTitle:@"视图"];
    [viewMenu addItemWithTitle:@"切换左侧边栏" action:@selector(toggleLeftSidebar:) keyEquivalent:@"b"];
    [viewMenu addItemWithTitle:@"切换白板/执行" action:@selector(toggleRightWorkbench:) keyEquivalent:@"j"];
    [viewMenu addItem:[NSMenuItem separatorItem]];
    [viewMenu addItemWithTitle:@"刷新界面" action:@selector(reloadPage:) keyEquivalent:@"r"];
    [viewMenuItem setSubmenu:viewMenu];

    NSMenuItem *winMenuItem = [[NSMenuItem alloc] init];
    [menubar addItem:winMenuItem];
    NSMenu *winMenu = [[NSMenu alloc] initWithTitle:@"窗口"];
    [winMenu addItemWithTitle:@"关闭窗口" action:@selector(performClose:) keyEquivalent:@"w"];
    [winMenu addItemWithTitle:@"最小化" action:@selector(performMiniaturize:) keyEquivalent:@"m"];
    [winMenu addItemWithTitle:@"缩放" action:@selector(performZoom:) keyEquivalent:@""];
    [winMenuItem setSubmenu:winMenu];
}

- (void)reloadPage:(id)sender {
    if (self.webView) [self.webView reload];
}

- (void)openFrontendSettings:(id)sender {
    [self ensureWindowVisible];
    if (self.webView) [self.webView evaluateJavaScript:@"window.__roundtableMenu && window.__roundtableMenu('settings')" completionHandler:nil];
}

- (void)createNewSession:(id)sender {
    [self ensureWindowVisible];
    if (self.webView) [self.webView evaluateJavaScript:@"window.__roundtableMenu && window.__roundtableMenu('newSession')" completionHandler:nil];
}

- (void)toggleLeftSidebar:(id)sender {
    [self ensureWindowVisible];
    if (self.webView) [self.webView evaluateJavaScript:@"window.__roundtableMenu && window.__roundtableMenu('toggleLeft')" completionHandler:nil];
}

- (void)toggleRightWorkbench:(id)sender {
    [self ensureWindowVisible];
    if (self.webView) [self.webView evaluateJavaScript:@"window.__roundtableMenu && window.__roundtableMenu('toggleRight')" completionHandler:nil];
}

- (void)ensureWindowVisible {
    if (self.window && !self.window.isVisible) {
        [self.window makeKeyAndOrderFront:nil];
    }
}

- (void)openNativeFolderSheet:(id)sender {
    [self ensureWindowVisible];
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.canChooseFiles = NO;
    panel.canChooseDirectories = YES;
    panel.allowsMultipleSelection = NO;
    panel.canCreateDirectories = YES;
    panel.prompt = @"绑定此目录";
    panel.message = @"请选择 AI圆桌 绑定的本地项目工作区目录：";

    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
        NSString *chosen = @"";
        if (result == NSModalResponseOK && panel.URL.path.length > 0) {
            chosen = panel.URL.path;
        }
        NSString *js = [NSString stringWithFormat:@"window.__onNativeFolderPicked && window.__onNativeFolderPicked('%@')",
                        escapeJsSingleQuoted(chosen)];
        [self.webView evaluateJavaScript:js completionHandler:nil];
    }];
}

- (void)userContentController:(WKUserContentController *)userContentController
      didReceiveScriptMessage:(WKScriptMessage *)message {
    if (![message.name isEqualToString:@"roundtableNative"]) return;
    if (![message.body isKindOfClass:[NSDictionary class]]) return;
    NSDictionary *dict = (NSDictionary *)message.body;
    NSString *action = dict[@"action"];
    if ([action isEqualToString:@"pickFolder"]) {
        [self openNativeFolderSheet:nil];
    } else if ([action isEqualToString:@"retryBoot"]) {
        [self stopBackendProcess];
        [self showBootingScreen];
        [self startEmbeddedBackend];
        [self pollAndLoadFrontend];
    }
}

- (void)stopBackendProcess {
    if (self.serverPid > 0) {
        kill(-self.serverPid, SIGTERM);
        kill(self.serverPid, SIGTERM);
        self.serverPid = 0;
    }
}

- (void)startEmbeddedBackend {
    self.serverPort = findAvailablePort(8765, 8799);
    NSString *resPath = [[NSBundle mainBundle] resourcePath];
    NSString *serverPy = [resPath stringByAppendingPathComponent:@"app/backend/server.py"];
    NSString *dataDir = [NSHomeDirectory() stringByAppendingPathComponent:@".ai-roundtable"];
    NSString *defaultWs = [dataDir stringByAppendingPathComponent:@"workspace"];
    self.bootLogPath = [dataDir stringByAppendingPathComponent:@"backend_boot.log"];

    [[NSFileManager defaultManager] createDirectoryAtPath:defaultWs
                              withIntermediateDirectories:YES
                                               attributes:nil
                                                    error:nil];

    NSString *escapedPy = [serverPy stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"];
    NSString *escapedWs = [defaultWs stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"];
    NSString *escapedLog = [self.bootLogPath stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"];
    NSString *cmd = [NSString stringWithFormat:@"AI_ROUNDTABLE_LOGIN_SHELL=1 exec python3 '%@' --host 127.0.0.1 --port %d --workspace '%@' > '%@' 2>&1",
                     escapedPy, self.serverPort, escapedWs, escapedLog];

    char *argv[] = { "zsh", "-lic", (char *)[cmd UTF8String], NULL };
    posix_spawnattr_t attr;
    posix_spawnattr_init(&attr);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP);
    posix_spawnattr_setpgroup(&attr, 0);

    pid_t pid = 0;
    if (posix_spawnp(&pid, "zsh", NULL, &attr, argv, environ) == 0 && pid > 0) {
        self.serverPid = pid;
    }
    posix_spawnattr_destroy(&attr);
}

- (void)showBootingScreen {
    NSString *bootHtml = @"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                         @"<style>"
                         @"html,body{margin:0;height:100vh;display:flex;flex-direction:column;gap:14px;align-items:center;justify-content:center;"
                         @"background:#f5f4fb;color:#4b5563;font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:13.5px;font-weight:500;}"
                         @".ring{width:34px;height:34px;border-radius:11px;background:linear-gradient(135deg,#5b5bd6,#3b63f6 55%,#0d9470);"
                         @"box-shadow:0 8px 24px rgba(91,91,214,0.22);animation:pulse 1.4s infinite ease-in-out;}"
                         @"@keyframes pulse{0%,100%{transform:scale(0.95);opacity:0.86}50%{transform:scale(1.06);opacity:1}}"
                         @"</style></head><body><div class='ring'></div><div>正在启动 AI圆桌 本地服务并探测 CLI 环境…</div></body></html>";
    [self.webView loadHTMLString:bootHtml baseURL:nil];
}

- (void)showBootErrorScreen:(NSString *)detail {
    NSString *safeLog = escapeHtmlString(detail.length > 0 ? detail : @"未捕获到详细标准错误输出，请确认系统已安装 python3。");
    NSString *errHtml = [NSString stringWithFormat:
        @"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        @"<style>"
        @"html,body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#f5f4fb;color:#18181b;font-family:-apple-system,BlinkMacSystemFont,sans-serif;}"
        @".card{max-width:560px;width:90%%;background:#fff;border-radius:20px;padding:24px 26px;box-shadow:0 16px 38px rgba(15,23,42,0.08);border:1px solid rgba(24,24,27,0.08);}"
        @"h3{margin:0 0 8px;font-size:16px;color:#dc2626;}"
        @"p{margin:0 0 12px;font-size:13px;color:#4b5563;line-height:1.6;}"
        @"pre{margin:0 0 16px;padding:10px 12px;background:#f1f5f9;border-radius:10px;font-size:11.5px;max-height:180px;overflow:auto;white-space:pre-wrap;word-break:break-all;color:#334155;}"
        @"button{background:linear-gradient(135deg,#5b5bd6,#3b63f6);color:#fff;border:none;border-radius:999px;padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer;}"
        @"</style></head><body><div class='card'>"
        @"<h3>本地服务启动超时或异常退出</h3>"
        @"<p>内置 Python 服务未能在预期时间内就绪，请检查终端环境配置（如 ~/.zshrc 中是否有阻塞交互命令）后点击下方重试：</p>"
        @"<pre>%@</pre>"
        @"<button onclick=\"window.webkit.messageHandlers.roundtableNative.postMessage({action:'retryBoot'})\">重新启动本地服务</button>"
        @"</div></body></html>",
        safeLog];
    [self.webView loadHTMLString:errHtml baseURL:nil];
}

- (void)pollAndLoadFrontend {
    NSURL *statusUrl = buildLocalURL(self.serverPort, @"/api/status");
    NSURL *appUrl = buildLocalURL(self.serverPort, @"/");
    pid_t launchedPid = self.serverPid;
    NSString *logPath = [self.bootLogPath copy];

    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        for (int i = 0; i < 240; i++) {
            if (launchedPid > 0) {
                int wstatus = 0;
                pid_t w = waitpid(launchedPid, &wstatus, WNOHANG);
                if (w == launchedPid) {
                    break;
                }
            }

            NSURLRequest *req = [NSURLRequest requestWithURL:statusUrl
                                                 cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                             timeoutInterval:0.25];
            dispatch_semaphore_t sem = dispatch_semaphore_create(0);
            __block BOOL ok = NO;
            [[[NSURLSession sharedSession] dataTaskWithRequest:req
                                             completionHandler:^(NSData *data, NSURLResponse *resp, NSError *error) {
                NSHTTPURLResponse *httpResp = (NSHTTPURLResponse *)resp;
                if (!error && httpResp.statusCode == 200) {
                    ok = YES;
                }
                dispatch_semaphore_signal(sem);
            }] resume];
            dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)));

            if (ok) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    NSURLRequest *mainReq = [NSURLRequest requestWithURL:appUrl];
                    [self.webView loadRequest:mainReq];
                });
                return;
            }
            [NSThread sleepForTimeInterval:0.04];
        }

        NSString *logTxt = [NSString stringWithContentsOfFile:logPath encoding:NSUTF8StringEncoding error:nil] ?: @"";
        if (logTxt.length > 1400) {
            logTxt = [logTxt substringFromIndex:(logTxt.length - 1400)];
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            [self showBootErrorScreen:logTxt];
        });
    });
}

- (BOOL)hasBusyBackendSession {
    if (self.serverPid <= 0 || self.serverPort <= 0) return NO;
    NSURL *statusUrl = buildLocalURL(self.serverPort, @"/api/status");
    NSURLRequest *req = [NSURLRequest requestWithURL:statusUrl
                                         cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                     timeoutInterval:0.25];
    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block BOOL busy = NO;
    [[[NSURLSession sharedSession] dataTaskWithRequest:req
                                     completionHandler:^(NSData *data, NSURLResponse *resp, NSError *error) {
        if (!error && data) {
            NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            NSDictionary *sys = [json isKindOfClass:[NSDictionary class]] ? json[@"system"] : nil;
            if ([sys isKindOfClass:[NSDictionary class]] && [sys[@"has_busy_session"] boolValue]) {
                busy = YES;
            }
        }
        dispatch_semaphore_signal(sem);
    }] resume];
    dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.28 * NSEC_PER_SEC)));
    return busy;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self setupMainMenu];
    [self startEmbeddedBackend];

    NSRect frame = NSMakeRect(0, 0, 1440, 880);
    NSUInteger style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                       NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable;
    self.window = [[NSWindow alloc] initWithContentRect:frame
                                              styleMask:style
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    [self.window setTitle:@"AI圆桌 — 多 CLI 协作工作台"];
    [self.window setMinSize:NSMakeSize(980, 620)];
    [self.window setBackgroundColor:[NSColor colorWithSRGBRed:0.961 green:0.957 blue:0.984 alpha:1.0]];
    [self.window setReleasedWhenClosed:NO];
    self.window.delegate = self;
    [self.window center];

    WKWebViewConfiguration *cfg = [[WKWebViewConfiguration alloc] init];
    [cfg.userContentController addScriptMessageHandler:self name:@"roundtableNative"];
    self.webView = [[WKWebView alloc] initWithFrame:self.window.contentView.bounds configuration:cfg];
    self.webView.autoresizingMask = NSViewWidthSizable | NSViewHeightSizable;
    self.webView.UIDelegate = self;
    self.webView.navigationDelegate = self;
    @try {
        [self.webView setValue:@NO forKey:@"drawsBackground"];
    } @catch (NSException *_) {
    }
    [self.window setContentView:self.webView];

    [self showBootingScreen];
    [self.window makeKeyAndOrderFront:nil];
    [NSApp activateIgnoringOtherApps:YES];

    [self pollAndLoadFrontend];
}

- (void)webView:(WKWebView *)webView
runJavaScriptAlertPanelWithMessage:(NSString *)message
initiatedByFrame:(WKFrameInfo *)frame
completionHandler:(void (^)(void))completionHandler {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"AI圆桌";
    alert.informativeText = message ?: @"";
    [alert addButtonWithTitle:@"确定"];
    [alert beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse returnCode) {
        completionHandler();
    }];
}

- (void)webView:(WKWebView *)webView
runJavaScriptConfirmPanelWithMessage:(NSString *)message
initiatedByFrame:(WKFrameInfo *)frame
completionHandler:(void (^)(BOOL result))completionHandler {
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"请确认操作";
    alert.informativeText = message ?: @"";
    [alert addButtonWithTitle:@"确认"];
    [alert addButtonWithTitle:@"取消"];
    [alert beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse returnCode) {
        completionHandler(returnCode == NSAlertFirstButtonReturn);
    }];
}

// 关闭窗口仅隐藏主窗口，不中断后台讨论与 Astra 执行；点击 Dock 图标即可立即恢复
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender {
    return NO;
}

- (BOOL)applicationShouldHandleReopen:(NSApplication *)theApplication hasVisibleWindows:(BOOL)flag {
    if (!flag && self.window) {
        [self.window makeKeyAndOrderFront:nil];
    }
    return YES;
}

- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender {
    if ([self hasBusyBackendSession]) {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.alertStyle = NSAlertStyleWarning;
        alert.messageText = @"当前有正在进行的圆桌讨论或执行任务";
        alert.informativeText = @"现在退出 AI圆桌 将立即终止后台正在运行的 CLI 进程。确定要退出吗？";
        [alert addButtonWithTitle:@"中止并退出"];
        [alert addButtonWithTitle:@"取消"];
        NSModalResponse resp = [alert runModal];
        if (resp != NSAlertFirstButtonReturn) {
            return NSTerminateCancel;
        }
    }
    return NSTerminateNow;
}

- (void)applicationWillTerminate:(NSNotification *)notification {
    [self stopBackendProcess];
}

@end

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        NSApplication *app = [NSApplication sharedApplication];
        [app setActivationPolicy:NSApplicationActivationPolicyRegular];
        AppDelegate *delegate = [[AppDelegate alloc] init];
        [app setDelegate:delegate];
        [app run];
    }
    return 0;
}
