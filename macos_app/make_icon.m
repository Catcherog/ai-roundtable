// AI圆桌 v4 — 3C「旋轮连续三叶结 (Guilloche Trefoil Knot)」macOS 超椭圆图标生成器
// 支持 72/144 DPI 全尺寸 Retina .iconset 输出，并支持可选第二参数直接导出高清 PNG 预览图
#import <Cocoa/Cocoa.h>
#include <math.h>

static NSColor *guillocheColorAtAngle(CGFloat angleRad, CGFloat strandRatio, CGFloat alpha) {
    // 严格 2*pi 周期余弦核函数，360° 全圆周零接缝平滑过渡
    CGFloat aCobalt = 7.0 * M_PI / 6.0;  // 左下 210°：雾紫钴蓝
    CGFloat aSage   = M_PI / 2.0;        // 顶部  90°：鼠尾草青翠
    CGFloat aAmber  = 11.0 * M_PI / 6.0; // 右下 330°：温润琥珀金

    CGFloat k1 = 0.5 * (1.0 + cos(angleRad - aCobalt));
    CGFloat k2 = 0.5 * (1.0 + cos(angleRad - aSage));
    CGFloat k3 = 0.5 * (1.0 + cos(angleRad - aAmber));

    CGFloat w1 = pow(k1, 2.6) + 0.05;
    CGFloat w2 = pow(k2, 2.6) + 0.05;
    CGFloat w3 = pow(k3, 2.6) + 0.05;
    CGFloat sum = w1 + w2 + w3;
    w1 /= sum; w2 /= sum; w3 /= sum;

    CGFloat lift = (strandRatio - 0.5) * 0.045;
    // 融入微雾紫调的钴蓝 (0.25, 0.35, 0.80) · 鼠尾草青绿 (0.15, 0.54, 0.45) · 暖琥珀金 (0.78, 0.49, 0.18)
    CGFloat r = w1 * 0.25 + w2 * 0.15 + w3 * 0.78 + lift;
    CGFloat g = w1 * 0.35 + w2 * 0.54 + w3 * 0.49 + lift;
    CGFloat b = w1 * 0.80 + w2 * 0.45 + w3 * 0.18 + lift;

    return [NSColor colorWithSRGBRed:fmin(1.0, fmax(0.0, r))
                               green:fmin(1.0, fmax(0.0, g))
                                blue:fmin(1.0, fmax(0.0, b))
                               alpha:alpha];
}

static void renderIconPNG(NSString *outPath, int pxSize, int ptSize) {
    NSBitmapImageRep *rep = [[NSBitmapImageRep alloc]
        initWithBitmapDataPlanes:NULL
                      pixelsWide:pxSize
                      pixelsHigh:pxSize
                   bitsPerSample:8
                 samplesPerPixel:4
                        hasAlpha:YES
                        isPlanar:NO
                  colorSpaceName:NSDeviceRGBColorSpace
                     bytesPerRow:0
                    bitsPerPixel:0];
    [rep setSize:NSMakeSize(ptSize, ptSize)];

    [NSGraphicsContext saveGraphicsState];
    NSGraphicsContext *ctx = [NSGraphicsContext graphicsContextWithBitmapImageRep:rep];
    ctx.imageInterpolation = NSImageInterpolationHigh;
    ctx.shouldAntialias = YES;
    [NSGraphicsContext setCurrentContext:ctx];

    NSAffineTransform *xform = [NSAffineTransform transform];
    [xform scaleBy:(CGFloat)ptSize / 1024.0];
    [xform concat];

    // 1. 温润珍珠雾紫微奶油 macOS 超椭圆底座 (#FAF8F4 -> #F5F3FB -> #F3EFE8)
    NSRect bgRect = NSMakeRect(68, 68, 888, 888);
    NSBezierPath *bgPath = [NSBezierPath bezierPathWithRoundedRect:bgRect xRadius:214 yRadius:214];

    [NSGraphicsContext saveGraphicsState];
    NSShadow *dropShadow = [[NSShadow alloc] init];
    dropShadow.shadowOffset = NSMakeSize(0, -14.0);
    dropShadow.shadowBlurRadius = 32.0;
    dropShadow.shadowColor = [NSColor colorWithSRGBRed:0.12 green:0.13 blue:0.22 alpha:0.15];
    [dropShadow set];
    [[NSColor colorWithSRGBRed:0.97 green:0.96 blue:0.95 alpha:1.0] setFill];
    [bgPath fill];
    [NSGraphicsContext restoreGraphicsState];

    NSGradient *bgGrad = [[NSGradient alloc] initWithColorsAndLocations:
        [NSColor colorWithSRGBRed:0.988 green:0.982 blue:0.968 alpha:1.0], 0.0,
        [NSColor colorWithSRGBRed:0.960 green:0.954 blue:0.984 alpha:1.0], 0.52,
        [NSColor colorWithSRGBRed:0.952 green:0.938 blue:0.910 alpha:1.0], 1.0, nil];
    [bgGrad drawInBezierPath:bgPath angle:310.0];

    [NSGraphicsContext saveGraphicsState];
    [bgPath addClip];

    // 2. 零中心伪影的极轻雾紫与暖琥珀漫反射微晕 (radius 从 0 起绘)
    NSGradient *mistGlow = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithSRGBRed:0.36 green:0.34 blue:0.82 alpha:0.06]
                                                         endingColor:[NSColor colorWithSRGBRed:0.36 green:0.34 blue:0.82 alpha:0.0]];
    [mistGlow drawFromCenter:NSMakePoint(300, 740) radius:0.0 toCenter:NSMakePoint(300, 740) radius:480.0 options:NSGradientDrawsBeforeStartingLocation];

    NSGradient *warmGlow = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithSRGBRed:0.82 green:0.52 blue:0.18 alpha:0.05]
                                                         endingColor:[NSColor colorWithSRGBRed:0.82 green:0.52 blue:0.18 alpha:0.0]];
    [warmGlow drawFromCenter:NSMakePoint(720, 290) radius:0.0 toCenter:NSMakePoint(720, 290) radius:440.0 options:NSGradientDrawsBeforeStartingLocation];

    // 3. 3C 核心图形：平滑无折角 (2,3)-旋轮连续三叶结（纯凸曲率圆桌内孔）
    CGFloat cx = 512.0;
    CGFloat cy = 498.0;
    int strandCount = (pxSize <= 48) ? 3 : ((pxSize <= 96) ? 6 : 10);
    int segSteps = (pxSize <= 64) ? 200 : 420;
    CGFloat baseStrokeWidth = (pxSize <= 48) ? 14.5 : ((pxSize <= 96) ? 6.0 : 3.25);

    for (int k = 0; k < strandCount; k++) {
        CGFloat u = (strandCount == 1) ? 0.5 : ((CGFloat)k / (CGFloat)(strandCount - 1));
        // 保持 Ak / Rk <= 0.35，令内环围合成圆润饱满的圆桌中心负空间，无任何内凹尖角
        CGFloat Rk = 190.0 + u * 46.0;   // 190 -> 236
        CGFloat Ak = 60.0  + u * 24.0;   // 60  -> 84 (圆润内孔 130..152，外峰 250..320)
        CGFloat phaseShift = (u - 0.5) * 0.14;
        CGFloat alpha = 0.80 + 0.16 * sin(u * M_PI);

        NSPoint prevPt = NSZeroPoint;
        for (int s = 0; s <= segSteps; s++) {
            CGFloat t = ((CGFloat)s / (CGFloat)segSteps) * (M_PI * 2.0);
            CGFloat r = Rk + Ak * cos(3.0 * t + phaseShift);
            CGFloat phi = 2.0 * t + (M_PI / 2.0);
            NSPoint pt = NSMakePoint(cx + r * cos(phi), cy + r * sin(phi));

            if (s > 0) {
                NSBezierPath *seg = [NSBezierPath bezierPath];
                [seg setLineCapStyle:NSLineCapStyleRound];
                [seg setLineJoinStyle:NSLineJoinStyleRound];
                [seg setLineWidth:baseStrokeWidth];
                [seg moveToPoint:prevPt];
                [seg lineToPoint:pt];

                CGFloat midAng = atan2((prevPt.y + pt.y) * 0.5 - cy, (prevPt.x + pt.x) * 0.5 - cx);
                [guillocheColorAtAngle(midAng, u, alpha) setStroke];
                [seg stroke];
            }
            prevPt = pt;
        }
    }

    [NSGraphicsContext restoreGraphicsState];

    // 4. 顶部高光玻璃内缘 + 1px 温润雾紫纸感细外框
    NSBezierPath *innerHighlight = [NSBezierPath bezierPathWithRoundedRect:NSInsetRect(bgRect, 2.5, 2.5) xRadius:211.5 yRadius:211.5];
    [innerHighlight setLineWidth:4.0];
    [[NSColor colorWithCalibratedWhite:1.0 alpha:0.82] setStroke];
    [innerHighlight stroke];

    NSBezierPath *outerHairline = [NSBezierPath bezierPathWithRoundedRect:bgRect xRadius:214 yRadius:214];
    [outerHairline setLineWidth:2.2];
    [[NSColor colorWithSRGBRed:0.44 green:0.42 blue:0.54 alpha:0.20] setStroke];
    [outerHairline stroke];

    [NSGraphicsContext restoreGraphicsState];

    NSData *pngData = [rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    [pngData writeToFile:outPath atomically:YES];
}

static BOOL writeIcnsFile(NSString *iconsetDir, NSString *icnsOutPath) {
    struct { const char *ostype; NSString *filename; } slots[10] = {
        {"icp4", @"icon_16x16.png"},
        {"ic11", @"icon_16x16@2x.png"},
        {"icp5", @"icon_32x32.png"},
        {"ic12", @"icon_32x32@2x.png"},
        {"ic07", @"icon_128x128.png"},
        {"ic13", @"icon_128x128@2x.png"},
        {"ic08", @"icon_256x256.png"},
        {"ic14", @"icon_256x256@2x.png"},
        {"ic09", @"icon_512x512.png"},
        {"ic10", @"icon_512x512@2x.png"},
    };
    NSMutableData *payload = [NSMutableData data];
    for (int i = 0; i < 10; i++) {
        NSString *p = [iconsetDir stringByAppendingPathComponent:slots[i].filename];
        NSData *png = [NSData dataWithContentsOfFile:p];
        if (!png || png.length == 0) return NO;
        uint32_t chunkLenBE = CFSwapInt32HostToBig((uint32_t)(8 + png.length));
        [payload appendBytes:slots[i].ostype length:4];
        [payload appendBytes:&chunkLenBE length:4];
        [payload appendData:png];
    }
    NSMutableData *icns = [NSMutableData dataWithCapacity:8 + payload.length];
    uint32_t totalLenBE = CFSwapInt32HostToBig((uint32_t)(8 + payload.length));
    [icns appendBytes:"icns" length:4];
    [icns appendBytes:&totalLenBE length:4];
    [icns appendData:payload];
    return [icns writeToFile:icnsOutPath atomically:YES];
}

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc < 2) return 1;
        NSString *iconsetDir = [NSString stringWithUTF8String:argv[1]];
        int sizes[5] = {16, 32, 128, 256, 512};
        for (int i = 0; i < 5; i++) {
            int s = sizes[i];
            NSString *p1 = [iconsetDir stringByAppendingPathComponent:[NSString stringWithFormat:@"icon_%dx%d.png", s, s]];
            NSString *p2 = [iconsetDir stringByAppendingPathComponent:[NSString stringWithFormat:@"icon_%dx%d@2x.png", s, s]];
            renderIconPNG(p1, s, s);
            renderIconPNG(p2, s * 2, s);
        }
        for (int a = 2; a < argc; a++) {
            NSString *arg = [NSString stringWithUTF8String:argv[a]];
            if ([arg isEqualToString:@"--icns"] && a + 1 < argc) {
                NSString *icnsPath = [NSString stringWithUTF8String:argv[++a]];
                if (!writeIcnsFile(iconsetDir, icnsPath)) return 2;
            } else {
                renderIconPNG(arg, 512, 512);
            }
        }
    }
    return 0;
}
