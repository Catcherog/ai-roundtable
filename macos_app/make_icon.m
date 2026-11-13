// 直接在目标 .iconset 目录生成符合 Apple iconutil 72/144 DPI 规范的全尺寸图标集
#import <Cocoa/Cocoa.h>

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
    [NSGraphicsContext setCurrentContext:ctx];

    NSAffineTransform *xform = [NSAffineTransform transform];
    [xform scaleBy:(CGFloat)ptSize / 1024.0];
    [xform concat];

    NSRect bgRect = NSMakeRect(64, 64, 896, 896);
    NSBezierPath *bgPath = [NSBezierPath bezierPathWithRoundedRect:bgRect xRadius:200 yRadius:200];
    NSGradient *grad = [[NSGradient alloc] initWithStartingColor:[NSColor colorWithDeviceRed:0.07 green:0.10 blue:0.16 alpha:1.0]
                                                     endingColor:[NSColor colorWithDeviceRed:0.12 green:0.18 blue:0.28 alpha:1.0]];
    [grad drawInBezierPath:bgPath angle:135.0];

    NSBezierPath *ring = [NSBezierPath bezierPathWithOvalInRect:NSMakeRect(282, 282, 460, 460)];
    [ring setLineWidth:20.0];
    [[NSColor colorWithDeviceWhite:1.0 alpha:0.18] setStroke];
    [ring stroke];

    NSBezierPath *tableCore = [NSBezierPath bezierPathWithOvalInRect:NSMakeRect(412, 412, 200, 200)];
    [[NSColor colorWithDeviceRed:0.18 green:0.25 blue:0.38 alpha:0.95] setFill];
    [tableCore fill];

    struct { CGFloat cx; CGFloat cy; CGFloat r; CGFloat g; CGFloat b; } nodes[3] = {
        {512, 742, 0.23, 0.51, 0.96},
        {313, 397, 0.96, 0.65, 0.14},
        {711, 397, 0.16, 0.78, 0.52}
    };
    for (int i = 0; i < 3; i++) {
        NSRect nr = NSMakeRect(nodes[i].cx - 76, nodes[i].cy - 76, 152, 152);
        NSBezierPath *np = [NSBezierPath bezierPathWithOvalInRect:nr];
        [[NSColor colorWithDeviceRed:nodes[i].r green:nodes[i].g blue:nodes[i].b alpha:1.0] setFill];
        [np fill];
        [np setLineWidth:10.0];
        [[NSColor colorWithDeviceWhite:1.0 alpha:0.88] setStroke];
        [np stroke];
    }

    [NSGraphicsContext restoreGraphicsState];

    NSData *pngData = [rep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
    [pngData writeToFile:outPath atomically:YES];
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
    }
    return 0;
}
