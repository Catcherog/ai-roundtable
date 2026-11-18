// AI圆桌.app — 原生 macOS (Cocoa + WKWebView) 桌面端入口（v4 原生多文件/图片选择器 + 安全凭据闭环 + 三态忙闲探针）
#import <Cocoa/Cocoa.h>
#import <Security/Security.h>
#import <WebKit/WebKit.h>
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <signal.h>
#include <spawn.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

typedef NS_ENUM(NSInteger, BackendBusyState) {
    BackendBusyStateIdle = 0,
    BackendBusyStateBusy = 1,
    BackendBusyStateUnknown = 2,
};

static NSString *generateSecureHex(size_t byteCount) {
    NSMutableData *buf = [NSMutableData dataWithLength:byteCount];
    if (SecRandomCopyBytes(kSecRandomDefault, byteCount, buf.mutableBytes) != errSecSuccess) {
        arc4random_buf(buf.mutableBytes, byteCount);
    }
    const unsigned char *bytes = (const unsigned char *)buf.bytes;
    NSMutableString *hex = [NSMutableString stringWithCapacity:byteCount * 2];
    for (size_t i = 0; i < byteCount; i++) {
        [hex appendFormat:@"%02x", bytes[i]];
    }
    return [hex copy];
}

// Keep the listener bound until the backend inherits it. Port 0 lets macOS
// choose an available port when every preferred port is in use.
static int reserveBackendListener(int *selectedPort) {
    for (int candidate = 8765; candidate <= 8800; candidate++) {
        int sock = socket(AF_INET, SOCK_STREAM, 0);
        if (sock < 0) return -1;
        if (fcntl(sock, F_SETFD, FD_CLOEXEC) < 0) {
            int err = errno;
            close(sock);
            errno = err;
            return -1;
        }
        int opt = 1;
        setsockopt(sock, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        struct sockaddr_in addr = {0};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(candidate <= 8799 ? candidate : 0);
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        socklen_t len = sizeof(addr);
        if (bind(sock, (struct sockaddr *)&addr, sizeof(addr)) == 0 &&
            listen(sock, SOMAXCONN) == 0 &&
            getsockname(sock, (struct sockaddr *)&addr, &len) == 0) {
            *selectedPort = ntohs(addr.sin_port);
            return sock;
        }
        int err = errno;
        close(sock);
        if (err != EADDRINUSE) {
            errno = err;
            return -1;
        }
    }
    errno = EADDRINUSE;
    return -1;
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

@interface AppDelegate : NSObject <NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandlerWithReply, NSWindowDelegate>
@property (nonatomic, strong) NSWindow *window;
@property (nonatomic, strong) WKWebView *webView;
@property (nonatomic, assign) pid_t serverPid;
@property (nonatomic, assign) int serverPort;
@property (nonatomic, copy) NSString *bootToken;
@property (nonatomic, copy) NSString *bootId;
@property (nonatomic, copy) NSString *bootLogPath;
@property (nonatomic, copy) NSString *bootLaunchError;
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
    [fileMenu addItemWithTitle:@"添加图片或文件附件…" action:@selector(openAttachmentPicker:) keyEquivalent:@"u"];
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

- (void)openAttachmentPicker:(id)sender {
    [self ensureWindowVisible];
    if (self.webView) [self.webView evaluateJavaScript:@"window.__roundtableMenu && window.__roundtableMenu('attachFiles')" completionHandler:nil];
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
    [self.webView evaluateJavaScript:@"window.__roundtableMenu && window.__roundtableMenu('pickFolder')" completionHandler:nil];
}

- (void)chooseFolderWithCompletion:(void (^)(NSString *))completion {
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
        completion(chosen);
    }];
}

// v4 关键能力：支持 WKWebView 内 <input type="file" multiple> 唤起原生 macOS 文件与图片选择面板
- (void)webView:(WKWebView *)webView
runOpenPanelWithParameters:(WKOpenPanelParameters *)parameters
initiatedByFrame:(WKFrameInfo *)frame
completionHandler:(void (^)(NSArray<NSURL *> * _Nullable URLs))completionHandler {
    if (![self isTrustedMainFrameOrigin:frame]) {
        completionHandler(nil);
        return;
    }
    NSOpenPanel *panel = [NSOpenPanel openPanel];
    panel.canChooseFiles = YES;
    panel.canChooseDirectories = NO;
    panel.allowsMultipleSelection = parameters.allowsMultipleSelection;
    panel.resolvesAliases = YES;
    panel.prompt = @"添加附件";
    panel.message = @"选择图片截图、源码、配置、日志或 PDF 文档加入当前圆桌研讨：";

    [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse result) {
        if (result == NSModalResponseOK && panel.URLs.count > 0) {
            completionHandler(panel.URLs);
        } else {
            completionHandler(nil);
        }
    }];
}

- (BOOL)isTrustedMainFrameOrigin:(WKFrameInfo *)frameInfo {
    if (!frameInfo || !frameInfo.isMainFrame) {
        return NO;
    }
    WKSecurityOrigin *origin = frameInfo.securityOrigin;
    if (!origin) return NO;
    BOOL protoOk = [origin.protocol.lowercaseString isEqualToString:@"http"];
    BOOL hostOk = [origin.host isEqualToString:@"127.0.0.1"];
    BOOL portOk = ((int)origin.port == self.serverPort);
    return protoOk && hostOk && portOk;
}

- (void)userContentController:(WKUserContentController *)userContentController
      didReceiveScriptMessage:(WKScriptMessage *)message
                 replyHandler:(void (^)(id, NSString *))replyHandler {
    if (![message.name isEqualToString:@"roundtableNative"] || ![message.body isKindOfClass:[NSDictionary class]]) {
        replyHandler(nil, @"无效的桌面操作");
        return;
    }
    NSDictionary *dict = (NSDictionary *)message.body;
    NSString *action = dict[@"action"];

    if ([action isEqualToString:@"retryBoot"]) {
        if (!message.frameInfo || !message.frameInfo.isMainFrame) {
            replyHandler(nil, @"拒绝非主框架启动调用");
            return;
        }
        replyHandler(@{@"ok": @YES}, nil);
        [self stopBackendProcess];
        [self showBootingScreen];
        [self startEmbeddedBackend];
        [self pollAndLoadFrontend];
        return;
    }

    if (![self isTrustedMainFrameOrigin:message.frameInfo]) {
        replyHandler(nil, @"拒绝非受信任源访问原生凭据桥");
        return;
    }

    if ([action isEqualToString:@"getBootAuth"]) {
        replyHandler(@{
            @"token": self.bootToken ?: @"",
            @"bootId": self.bootId ?: @"",
            @"port": @(self.serverPort),
        }, nil);
    } else if ([action isEqualToString:@"reissueBootstrap"]) {
        [self requestFreshBootstrapCodeWithCompletion:^(NSString *freshCode, NSString *errMsg) {
            if (freshCode.length > 0) {
                replyHandler(@{@"code": freshCode, @"bootId": self.bootId ?: @""}, nil);
            } else {
                replyHandler(nil, errMsg ?: @"重签一次性兑换码失败");
            }
        }];
    } else if ([action isEqualToString:@"pickFolder"]) {
        [self chooseFolderWithCompletion:^(NSString *chosen) { replyHandler(chosen, nil); }];
    } else if ([action isEqualToString:@"saveMinutes"]) {
        NSString *text = dict[@"text"];
        NSString *name = dict[@"filename"];
        if (![text isKindOfClass:[NSString class]] || ![name isKindOfClass:[NSString class]] || !text.length) {
            replyHandler(nil, @"会议纪要为空或文件名无效");
            return;
        }
        NSSavePanel *panel = [NSSavePanel savePanel];
        panel.title = @"保存会议纪要";
        panel.nameFieldStringValue = name.lastPathComponent;
        panel.canCreateDirectories = YES;
        [panel beginSheetModalForWindow:self.window completionHandler:^(NSModalResponse response) {
            if (response != NSModalResponseOK || !panel.URL) {
                replyHandler(@{@"cancelled": @YES}, nil);
                return;
            }
            NSError *error = nil;
            BOOL saved = [text writeToURL:panel.URL atomically:YES encoding:NSUTF8StringEncoding error:&error];
            replyHandler(saved ? @{@"ok": @YES} : nil, saved ? nil : error.localizedDescription);
        }];
    } else {
        replyHandler(nil, @"未知的桌面操作");
    }
}

- (void)requestFreshBootstrapCodeWithCompletion:(void (^)(NSString * _Nullable, NSString * _Nullable))completion {
    if (self.serverPort <= 0 || self.bootToken.length == 0) {
        completion(nil, @"本地服务尚未就绪");
        return;
    }
    NSURL *reissueUrl = buildLocalURL(self.serverPort, @"/api/auth/reissue-bootstrap");
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:reissueUrl
                                                       cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                   timeoutInterval:2.0];
    req.HTTPMethod = @"POST";
    [req setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    [req setValue:[NSString stringWithFormat:@"127.0.0.1:%d", self.serverPort] forHTTPHeaderField:@"Host"];
    [req setValue:self.bootToken forHTTPHeaderField:@"X-Roundtable-Token"];
    req.HTTPBody = [@"{}" dataUsingEncoding:NSUTF8StringEncoding];

    [[[NSURLSession sharedSession] dataTaskWithRequest:req
                                     completionHandler:^(NSData *data, NSURLResponse *resp, NSError *error) {
        NSHTTPURLResponse *httpResp = (NSHTTPURLResponse *)resp;
        NSString *code = nil;
        if (!error && httpResp.statusCode == 200 && data) {
            NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if ([json isKindOfClass:[NSDictionary class]] && [json[@"bootstrap_code"] isKindOfClass:[NSString class]]) {
                code = json[@"bootstrap_code"];
            }
        }
        dispatch_async(dispatch_get_main_queue(), ^{
            completion(code, error.localizedDescription);
        });
    }] resume];
}

- (void)webViewWebContentProcessDidTerminate:(WKWebView *)webView {
    [self requestFreshBootstrapCodeWithCompletion:^(NSString *freshCode, NSString *errMsg) {
        NSURL *baseAppUrl = buildLocalURL(self.serverPort, @"/");
        if (freshCode.length > 0) {
            NSString *withHash = [NSString stringWithFormat:@"%@#bootstrap=%@", baseAppUrl.absoluteString, freshCode];
            NSURL *reloadUrl = [NSURL URLWithString:withHash];
            if (reloadUrl) {
                [webView loadRequest:[NSURLRequest requestWithURL:reloadUrl]];
                return;
            }
        }
        [webView loadRequest:[NSURLRequest requestWithURL:baseAppUrl]];
    }];
}

- (void)stopBackendProcess {
    if (self.serverPid > 0) {
        pid_t pid = self.serverPid;
        self.serverPid = 0;
        int st = 0;
        pid_t result = waitpid(pid, &st, WNOHANG);
        if (result == pid || (result < 0 && errno == ECHILD)) return;
        kill(-pid, SIGTERM);
        kill(pid, SIGTERM);
        usleep(120000);
        kill(-pid, SIGKILL);
        while (waitpid(pid, &st, 0) < 0 && errno == EINTR) {}
    }
}

- (void)startEmbeddedBackend {
    self.serverPort = 0;
    self.bootLaunchError = nil;
    self.bootToken = generateSecureHex(32);
    self.bootId = generateSecureHex(16);
    int port = 0;
    int listener = reserveBackendListener(&port);
    if (listener < 0) {
        self.bootLaunchError = [NSString stringWithFormat:@"本地服务无法监听回环地址：%s", strerror(errno)];
        return;
    }
    self.serverPort = port;
    const int childListener = listener == 3 ? 4 : 3;

    NSString *resPath = [[NSBundle mainBundle] resourcePath];
    NSString *serverPy = [resPath stringByAppendingPathComponent:@"app/backend/server.py"];
    NSString *dataDir = [[NSProcessInfo processInfo].environment[@"AI_ROUNDTABLE_HOME"] stringByExpandingTildeInPath];
    if (dataDir.length == 0) {
        dataDir = [NSHomeDirectory() stringByAppendingPathComponent:@".ai-roundtable"];
    }
    NSString *defaultWs = [dataDir stringByAppendingPathComponent:@"workspace"];
    self.bootLogPath = [dataDir stringByAppendingPathComponent:@"backend_boot.log"];

    [[NSFileManager defaultManager] createDirectoryAtPath:defaultWs
                              withIntermediateDirectories:YES
                                               attributes:nil
                                                    error:nil];

    NSMutableDictionary<NSString *, NSString *> *envMap = [NSMutableDictionary dictionary];
    for (char **ep = environ; ep && *ep; ep++) {
        NSString *entry = [NSString stringWithUTF8String:*ep];
        if (!entry) continue;
        NSRange eq = [entry rangeOfString:@"="];
        if (eq.location != NSNotFound) {
            NSString *k = [entry substringToIndex:eq.location];
            NSString *v = [entry substringFromIndex:(eq.location + 1)];
            envMap[k] = v;
        }
    }
    envMap[@"AI_ROUNDTABLE_LOGIN_SHELL"] = @"1";
    envMap[@"PYTHONDONTWRITEBYTECODE"] = @"1";
    envMap[@"AI_ROUNDTABLE_BOOT_TOKEN"] = self.bootToken;
    envMap[@"AI_ROUNDTABLE_BOOT_ID"] = self.bootId;
    [envMap removeObjectForKey:@"AI_ROUNDTABLE_BOOTSTRAP_CODE"];

    NSUInteger envCount = envMap.count;
    char **childEnv = (char **)calloc(envCount + 1, sizeof(char *));
    NSUInteger idx = 0;
    for (NSString *k in envMap) {
        NSString *kv = [NSString stringWithFormat:@"%@=%@", k, envMap[k]];
        childEnv[idx++] = strdup([kv UTF8String]);
    }
    childEnv[idx] = NULL;

    NSString *escapedPy = [serverPy stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"];
    NSString *escapedWs = [defaultWs stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"];
    NSString *escapedLog = [self.bootLogPath stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"];
    NSString *cmd = [NSString stringWithFormat:@"exec python3 '%@' --host 127.0.0.1 --port %d --listen-fd %d --workspace '%@' > '%@' 2>&1",
                     escapedPy, port, childListener, escapedWs, escapedLog];

    char *argv[] = { "zsh", "-lic", (char *)[cmd UTF8String], NULL };
    posix_spawnattr_t attr;
    posix_spawnattr_init(&attr);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_SETPGROUP);
    posix_spawnattr_setpgroup(&attr, 0);

    pid_t pid = 0;
    posix_spawn_file_actions_t actions;
    int launchStatus = posix_spawn_file_actions_init(&actions);
    if (launchStatus == 0) {
        launchStatus = posix_spawn_file_actions_adddup2(&actions, listener, childListener);
        if (launchStatus == 0) launchStatus = posix_spawnp(&pid, "zsh", &actions, &attr, argv, childEnv);
        posix_spawn_file_actions_destroy(&actions);
    }
    close(listener);
    if (launchStatus == 0 && pid > 0) {
        self.serverPid = pid;
    } else {
        self.bootLaunchError = [NSString stringWithFormat:@"无法启动本地服务进程：%s", strerror(launchStatus)];
    }
    posix_spawnattr_destroy(&attr);

    for (NSUInteger i = 0; i < idx; i++) {
        free(childEnv[i]);
    }
    free(childEnv);
}

- (void)showBootingScreen {
    NSString *bootHtml = @"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        @"<style>"
        @"html,body{margin:0;height:100vh;display:flex;flex-direction:column;gap:16px;align-items:center;justify-content:center;"
        @"background:#f4f5fa;color:#475569;font-family:-apple-system,BlinkMacSystemFont,sans-serif;font-size:13.5px;font-weight:500;}"
        @".orbit-stage{position:relative;width:62px;height:62px;border-radius:18px;background:linear-gradient(145deg,#ffffff,#eef0fb);"
        @"box-shadow:0 12px 30px rgba(79,70,229,0.14),inset 0 1px 0 #fff;display:flex;align-items:center;justify-content:center;}"
        @".node{position:absolute;width:9px;height:9px;border-radius:999px;will-change:transform,opacity;}"
        @".n1{background:#3b63f6;animation:orb1 1.8s infinite cubic-bezier(0.34,1.45,0.64,1);}"
        @".n2{background:#d97706;animation:orb2 1.8s infinite cubic-bezier(0.34,1.45,0.64,1);}"
        @".n3{background:#0d9470;animation:orb3 1.8s infinite cubic-bezier(0.34,1.45,0.64,1);}"
        @".core{width:18px;height:18px;border-radius:6px;transform:rotate(45deg);background:linear-gradient(135deg,#4f46e5,#0d9470);opacity:0.26;animation:coreBreathe 1.8s infinite ease-in-out;}"
        @"@keyframes orb1{0%,100%{transform:translate(0,-17px) scale(1)}33%{transform:translate(15px,10px) scale(0.86)}66%{transform:translate(-15px,10px) scale(0.92)}}"
        @"@keyframes orb2{0%,100%{transform:translate(15px,10px) scale(0.92)}33%{transform:translate(-15px,10px) scale(1)}66%{transform:translate(0,-17px) scale(0.86)}}"
        @"@keyframes orb3{0%,100%{transform:translate(-15px,10px) scale(0.86)}33%{transform:translate(0,-17px) scale(0.92)}66%{transform:translate(15px,10px) scale(1)}}"
        @"@keyframes coreBreathe{0%,100%{transform:rotate(45deg) scale(0.88);opacity:0.18}50%{transform:rotate(45deg) scale(1.16);opacity:0.38}}"
        @"</style></head><body>"
        @"<div class='orbit-stage'><div class='core'></div><div class='node n1'></div><div class='node n2'></div><div class='node n3'></div></div>"
        @"<div>正在启动 AI圆桌 v4 多模态协同工作台…</div></body></html>";
    [self.webView loadHTMLString:bootHtml baseURL:nil];
}

- (void)showBootErrorScreen:(NSString *)detail {
    NSString *log = [detail stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSString *reason = [log componentsSeparatedByCharactersInSet:NSCharacterSet.newlineCharacterSet].lastObject;
    NSString *safeReason = escapeHtmlString(reason.length ? reason : @"未收到本地服务的启动响应。");
    NSString *safeLog = escapeHtmlString(log);
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
        @"<h3>本地服务未就绪</h3>"
        @"<p>%@</p>"
        @"<details style='margin-bottom:16px'><summary>查看启动日志</summary><pre>%@</pre></details>"
        @"<button onclick=\"window.webkit.messageHandlers.roundtableNative.postMessage({action:'retryBoot'})\">重新启动本地服务</button>"
        @"</div></body></html>",
        safeReason, safeLog];
    [self.webView loadHTMLString:errHtml baseURL:nil];
}

- (void)pollAndLoadFrontend {
    if (self.bootLaunchError) {
        [self showBootErrorScreen:self.bootLaunchError];
        return;
    }
    NSURL *statusUrl = buildLocalURL(self.serverPort, @"/api/status");
    NSURL *appUrl = buildLocalURL(self.serverPort, @"/");
    pid_t launchedPid = self.serverPid;
    NSString *expectedToken = [self.bootToken copy];
    NSString *expectedBootId = [self.bootId copy];
    NSString *logPath = [self.bootLogPath copy];

    dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        for (int i = 0; i < 240; i++) {
            if (launchedPid > 0) {
                siginfo_t info = {0};
                int rc = waitid(P_PID, (id_t)launchedPid, &info, WEXITED | WNOHANG | WNOWAIT);
                if ((rc == 0 && info.si_pid == launchedPid) || (rc < 0 && errno == ECHILD)) {
                    break;
                }
            }

            NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:statusUrl
                                                               cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                           timeoutInterval:0.28];
            [req setValue:(expectedToken ?: @"") forHTTPHeaderField:@"X-Roundtable-Token"];
            dispatch_semaphore_t sem = dispatch_semaphore_create(0);
            __block BOOL verified = NO;
            [[[NSURLSession sharedSession] dataTaskWithRequest:req
                                             completionHandler:^(NSData *data, NSURLResponse *resp, NSError *error) {
                NSHTTPURLResponse *httpResp = (NSHTTPURLResponse *)resp;
                if (!error && httpResp.statusCode == 200 && data) {
                    NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
                    if ([json isKindOfClass:[NSDictionary class]]) {
                        NSString *remoteBootId = json[@"boot_id"];
                        if ([remoteBootId isKindOfClass:[NSString class]] && [remoteBootId isEqualToString:expectedBootId]) {
                            verified = YES;
                        }
                    }
                }
                dispatch_semaphore_signal(sem);
            }] resume];
            dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.32 * NSEC_PER_SEC)));

            if (verified) {
                dispatch_async(dispatch_get_main_queue(), ^{
                    if (![self.bootId isEqualToString:expectedBootId]) return;
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
            if ([self.bootId isEqualToString:expectedBootId]) [self showBootErrorScreen:logTxt];
        });
    });
}

- (BackendBusyState)queryBackendBusyState {
    if (self.serverPid <= 0 || self.serverPort <= 0) return BackendBusyStateIdle;
    int wstatus = 0;
    pid_t result = waitpid(self.serverPid, &wstatus, WNOHANG);
    if (result == self.serverPid || (result < 0 && errno == ECHILD)) {
        self.serverPid = 0;
        return BackendBusyStateIdle;
    }

    NSURL *statusUrl = buildLocalURL(self.serverPort, @"/api/status");
    NSMutableURLRequest *req = [NSMutableURLRequest requestWithURL:statusUrl
                                                       cachePolicy:NSURLRequestReloadIgnoringLocalCacheData
                                                   timeoutInterval:0.35];
    [req setValue:(self.bootToken ?: @"") forHTTPHeaderField:@"X-Roundtable-Token"];
    NSString *expectedBootId = [self.bootId copy];

    dispatch_semaphore_t sem = dispatch_semaphore_create(0);
    __block BackendBusyState state = BackendBusyStateUnknown;
    [[[NSURLSession sharedSession] dataTaskWithRequest:req
                                     completionHandler:^(NSData *data, NSURLResponse *resp, NSError *error) {
        NSHTTPURLResponse *httpResp = (NSHTTPURLResponse *)resp;
        if (!error && httpResp.statusCode == 200 && data) {
            NSDictionary *json = [NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
            if ([json isKindOfClass:[NSDictionary class]]) {
                NSString *remoteBootId = json[@"boot_id"];
                NSDictionary *sys = json[@"system"];
                if ([remoteBootId isKindOfClass:[NSString class]]
                    && [remoteBootId isEqualToString:expectedBootId]
                    && [sys isKindOfClass:[NSDictionary class]]) {
                    state = [sys[@"has_busy_session"] boolValue] ? BackendBusyStateBusy : BackendBusyStateIdle;
                }
            }
        }
        dispatch_semaphore_signal(sem);
    }] resume];
    dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.42 * NSEC_PER_SEC)));
    return state;
}

- (void)applicationDidFinishLaunching:(NSNotification *)notification {
    [self setupMainMenu];
    [self startEmbeddedBackend];

    NSRect frame = NSMakeRect(0, 0, 1460, 900);
    NSUInteger style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
                       NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable;
    self.window = [[NSWindow alloc] initWithContentRect:frame
                                              styleMask:style
                                                backing:NSBackingStoreBuffered
                                                  defer:NO];
    [self.window setTitle:@"AI圆桌 — 多模态协同研讨与工程交付工作台"];
    [self.window setMinSize:NSMakeSize(980, 620)];
    [self.window setBackgroundColor:[NSColor colorWithSRGBRed:0.957 green:0.961 blue:0.980 alpha:1.0]];
    [self.window setReleasedWhenClosed:NO];
    self.window.delegate = self;
    [self.window center];

    WKWebViewConfiguration *cfg = [[WKWebViewConfiguration alloc] init];
    [cfg.userContentController addScriptMessageHandlerWithReply:self contentWorld:WKContentWorld.pageWorld name:@"roundtableNative"];
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
    BackendBusyState busyState = [self queryBackendBusyState];
    if (busyState != BackendBusyStateIdle) {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.alertStyle = NSAlertStyleWarning;
        if (busyState == BackendBusyStateBusy) {
            alert.messageText = @"当前有正在进行的圆桌讨论或代码执行任务";
            alert.informativeText = @"现在退出 AI圆桌 将立即终止后台正在运行的 CLI 进程组，并在下次启动时进入恢复确认流程。确定要退出吗？";
        } else {
            alert.messageText = @"无法立即确认后台任务空闲状态（Unknown）";
            alert.informativeText = @"本地后端可能正在执行高负载快照扫描或响应繁忙。强制退出将立即终止所有子进程组，确定要退出吗？";
        }
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
