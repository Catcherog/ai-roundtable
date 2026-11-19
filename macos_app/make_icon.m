// AI圆桌 v5.5 — 经典 3D 环面三叶结 (Classical Torus Trefoil) 光学水晶折射 + 轻纱极光丝带物理渲染器
// 零网格分块伪影、精确线段解析投影、深邃宝石芯折射色散与锐利欧根纱丝边，高精度还原图2视觉
#import <Cocoa/Cocoa.h>
#import <dispatch/dispatch.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    float r, g, b;
} Vec3;

static inline float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}

static inline float smoothstepf(float e0, float e1, float x) {
    float t = clampf((x - e0) / (e1 - e0), 0.0f, 1.0f);
    return t * t * (3.0f - 2.0f * t);
}

static inline Vec3 v3(float r, float g, float b) {
    Vec3 c = { r, g, b };
    return c;
}

static inline Vec3 v3_add(Vec3 a, Vec3 b) {
    return v3(a.r + b.r, a.g + b.g, a.b + b.b);
}

static inline Vec3 v3_scale(Vec3 a, float s) {
    return v3(a.r * s, a.g * s, a.b * s);
}

static inline Vec3 v3_mix(Vec3 a, Vec3 b, float t) {
    return v3(a.r + (b.r - a.r) * t, a.g + (b.g - a.g) * t, a.b + (b.b - a.b) * t);
}

// 经典圆润大开孔 3D 环面三叶结离散段（360 段连续折线胶囊解析求交，零空间分块伪影）
#define KNOT_SEGS 360

typedef struct {
    float x, y, z;
    float nx, ny;
    float t;
    Vec3 bodyTint;     // 水晶深层宝石吸收色
    Vec3 causticA;     // 内部主虹彩焦散色
    Vec3 causticB;     // 内部副虹彩焦散色
} KnotVertex;

static void buildClassicalTrefoil(KnotVertex *verts) {
    const float cx = 0.496f;
    const float cy = 0.472f;
    const float scale = 0.0945f; // 外峰半径 ~ 3 * 0.0945 = 0.2835，圆润大气饱满
    const float rot = -0.085f;   // 轻微顺时针灵动倾角，对齐图2顶环微偏姿态
    const float cosR = cosf(rot);
    const float sinR = sinf(rot);

    for (int i = 0; i <= KNOT_SEGS; i++) {
        float t = ((float)i / (float)KNOT_SEGS) * (float)(M_PI * 2.0);
        // 经典无拐点圆润环面三叶结方程：
        // t = pi -> 顶部高环峰值 (0, +3)
        // t = pi/3 -> 右下暖琥珀环峰值 (+2.60, -1.5)
        // t = 5*pi/3 -> 左下青翠环峰值 (-2.60, -1.5)
        float xr = sinf(t) + 2.0f * sinf(2.0f * t);
        float yr = 2.0f * cosf(2.0f * t) - cosf(t);
        float zr = sinf(3.0f * t);

        float px = cx + (xr * cosR - yr * sinR) * scale;
        float py = cy + (xr * sinR + yr * cosR) * scale * 1.03f;

        verts[i].x = px;
        verts[i].y = py;
        verts[i].z = zr;
        verts[i].t = t;

        // 按三叶空间方位赋予通透宝石水晶色相：
        // 顶叶 (90°): 蓝紫薰衣草水晶 | 左下叶 (210°): 冰川孔雀青翠水晶 | 右下叶 (330°): 暖香槟蜜桃金水晶
        float ang = atan2f(py - cy, px - cx);
        float wTop   = powf(0.5f + 0.5f * cosf(ang - 1.56f), 2.2f) + 0.05f;
        float wLeft  = powf(0.5f + 0.5f * cosf(ang - 3.68f), 2.2f) + 0.05f;
        float wRight = powf(0.5f + 0.5f * cosf(ang + 0.54f), 2.2f) + 0.05f;
        float wSum = wTop + wLeft + wRight;
        wTop /= wSum; wLeft /= wSum; wRight /= wSum;

        Vec3 bTop   = v3(0.38f, 0.42f, 0.96f);
        Vec3 bLeft  = v3(0.08f, 0.80f, 0.78f);
        Vec3 bRight = v3(1.00f, 0.54f, 0.28f);
        verts[i].bodyTint = v3_add(v3_add(v3_scale(bTop, wTop), v3_scale(bLeft, wLeft)), v3_scale(bRight, wRight));

        Vec3 c1Top   = v3(0.80f, 0.70f, 1.00f);
        Vec3 c1Left  = v3(0.38f, 1.00f, 0.88f);
        Vec3 c1Right = v3(1.00f, 0.80f, 0.46f);
        verts[i].causticA = v3_add(v3_add(v3_scale(c1Top, wTop), v3_scale(c1Left, wLeft)), v3_scale(c1Right, wRight));

        Vec3 c2Top   = v3(0.42f, 0.86f, 1.00f);
        Vec3 c2Left  = v3(0.44f, 0.68f, 1.00f);
        Vec3 c2Right = v3(0.98f, 0.60f, 0.76f);
        verts[i].causticB = v3_add(v3_add(v3_scale(c2Top, wTop), v3_scale(c2Left, wLeft)), v3_scale(c2Right, wRight));
    }

    for (int i = 0; i <= KNOT_SEGS; i++) {
        int prev = (i == 0) ? (KNOT_SEGS - 1) : (i - 1);
        int next = (i == KNOT_SEGS) ? 1 : (i + 1);
        float dx = verts[next].x - verts[prev].x;
        float dy = verts[next].y - verts[prev].y;
        float len = hypotf(dx, dy) + 1e-6f;
        verts[i].nx = -dy / len;
        verts[i].ny =  dx / len;
    }
}

// 真实单侧渐隐欧根纱褶皱片（一侧为细腻折光丝边，向内平滑过渡为半透明薄纱，消除硬直线交叉感）
static Vec3 evalSilkPleat(float dSigned, Vec3 edgeCol, Vec3 bodyCol, float width, float opacity) {
    float q = dSigned / width;
    if (q < -0.35f || q > 1.85f || opacity <= 0.001f) return v3(0.0f, 0.0f, 0.0f);
    // q = 0 处为纱褶亮脊，向 q > 0 侧柔滑铺展成轻透薄纱面
    float crest = expf(-q * q * 58.0f) * 0.56f;
    float sheer = (q >= 0.0f ? expf(-q * 1.95f) : expf(-q * q * 24.0f)) * 0.24f;
    Vec3 col = v3_mix(bodyCol, edgeCol, clampf(crest / (crest + sheer + 1e-4f) * 1.15f, 0.0f, 1.0f));
    return v3_scale(col, (crest + sheer) * opacity);
}

static void renderBackdropAndOrganza(Vec3 *bgBuf, int N) {
    typedef struct { float x, y, r; Vec3 col; float alpha; } BokehSpec;
    const BokehSpec bokehs[] = {
        { 0.652f, 0.758f, 0.033f, {1.00f, 0.72f, 0.80f}, 0.26f },
        { 0.772f, 0.672f, 0.035f, {0.38f, 0.95f, 0.96f}, 0.27f },
        { 0.785f, 0.758f, 0.028f, {0.50f, 0.88f, 0.92f}, 0.18f },
        { 0.490f, 0.858f, 0.026f, {0.58f, 0.66f, 0.94f}, 0.15f },
        { 0.592f, 0.836f, 0.021f, {0.70f, 0.68f, 0.96f}, 0.13f },
        { 0.718f, 0.818f, 0.025f, {0.86f, 0.70f, 0.94f}, 0.17f },
        { 0.852f, 0.578f, 0.014f, {0.56f, 0.86f, 1.00f}, 0.22f },
        { 0.176f, 0.278f, 0.024f, {0.70f, 0.54f, 0.94f}, 0.15f },
        { 0.246f, 0.242f, 0.018f, {0.92f, 0.66f, 0.86f}, 0.17f },
        { 0.376f, 0.168f, 0.022f, {0.40f, 0.86f, 0.88f}, 0.14f },
        { 0.396f, 0.198f, 0.013f, {0.55f, 0.96f, 0.90f}, 0.20f },
        { 0.882f, 0.166f, 0.019f, {1.00f, 0.86f, 0.76f}, 0.25f },
        { 0.295f, 0.822f, 0.029f, {0.34f, 0.60f, 0.96f}, 0.12f },
    };
    const int bokehCount = (int)(sizeof(bokehs) / sizeof(bokehs[0]));
    const BokehSpec *bokehPtr = bokehs;

    dispatch_apply(N, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t py) {
        float v = ((float)py + 0.5f) / (float)N;
        for (int px = 0; px < N; px++) {
            float u = ((float)px + 0.5f) / (float)N;

            // 1. 深邃夜空靛紫底色 + 右上柔美梦幻粉紫青星云漫射
            Vec3 base = v3(0.032f, 0.048f, 0.165f);
            float diag = clampf(u * 0.62f + (1.0f - v) * 0.38f, 0.0f, 1.0f);
            base = v3_mix(base, v3(0.145f, 0.115f, 0.325f), diag);

            float dUR = hypotf((u - 0.71f) * 1.02f, (v - 0.75f) * 1.08f);
            base = v3_add(base, v3_scale(v3(0.54f, 0.44f, 0.74f), expf(-dUR * dUR * 4.4f) * 0.76f));

            float dRC = hypotf(u - 0.78f, v - 0.63f);
            base = v3_add(base, v3_scale(v3(0.20f, 0.54f, 0.68f), expf(-dRC * dRC * 10.5f) * 0.38f));

            float dBL = hypotf(u - 0.24f, v - 0.22f);
            base = v3_add(base, v3_scale(v3(0.24f, 0.15f, 0.42f), expf(-dBL * dBL * 5.8f) * 0.42f));

            float dBR = hypotf(u - 0.76f, v - 0.16f);
            base = v3_add(base, v3_scale(v3(0.36f, 0.25f, 0.44f), expf(-dBR * dBR * 5.2f) * 0.44f));

            // 2. 柔焦镜头圆形散景光斑 (Bokeh)
            for (int b = 0; b < bokehCount; b++) {
                float d = hypotf(u - bokehPtr[b].x, v - bokehPtr[b].y) / bokehPtr[b].r;
                if (d < 1.22f) {
                    float disc = 1.0f - smoothstepf(0.72f, 1.15f, d);
                    float rim = expf(-powf(d - 0.80f, 2.0f) * 18.0f) * 0.24f;
                    base = v3_add(base, v3_scale(bokehPtr[b].col, (disc + rim) * bokehPtr[b].alpha));
                }
            }

            // 3. 贯通无交叉 S 型波浪多层欧根纱褶（1:1 对齐图2四角柔顺丝绸走势）
            // (a) 左侧至左上连续三层波浪轻纱（从左下边缘顺滑S型蜿蜒至顶部中左，无生硬交叉）
            {
                float spine1 = 0.11f + 0.34f * powf(v, 1.45f) + 0.046f * sinf(v * 7.2f + 0.4f);
                float spine2 = 0.04f + 0.25f * powf(v, 1.35f) + 0.052f * sinf(v * 5.8f + 2.1f);
                float spine3 = 0.16f + 0.37f * powf(v, 1.55f) + 0.036f * cosf(v * 8.4f + 1.1f);

                Vec3 mintEdge = v3_mix(v3(0.24f, 0.88f, 0.96f), v3(0.36f, 0.98f, 0.80f), smoothstepf(0.35f, 0.85f, v));
                mintEdge = v3_mix(mintEdge, v3(1.00f, 0.74f, 0.46f), smoothstepf(0.84f, 0.99f, v));
                Vec3 royalBody = v3_mix(v3(0.08f, 0.34f, 0.92f), v3(0.48f, 0.28f, 0.90f), expf(-powf(v - 0.56f, 2.0f) * 22.0f));

                // 纱褶自内缘 spine 向左上方铺展 (spine - u)
                base = v3_add(base, evalSilkPleat(spine1 - u, mintEdge, royalBody, 0.13f, 0.92f));
                base = v3_add(base, evalSilkPleat(spine2 - u, v3(0.28f, 0.64f, 1.00f), v3(0.08f, 0.28f, 0.86f), 0.11f, 0.78f));
                base = v3_add(base, evalSilkPleat(spine3 - u, mintEdge, v3(0.16f, 0.68f, 0.82f), 0.085f, 0.62f * smoothstepf(0.45f, 0.72f, v)));
            }

            // (b) 右上角贴边青翠薄荷轻纱（贴合右上超椭圆边缘柔美垂落，不与右下暖纱交叉）
            {
                float spineTR1 = 0.84f + 0.12f * (1.0f - v) + 0.035f * sinf(v * 7.6f + 0.5f);
                float spineTR2 = 0.90f + 0.08f * (1.0f - v) + 0.028f * cosf(v * 6.4f + 1.6f);
                float fadeTR = smoothstepf(0.38f, 0.62f, v);
                Vec3 edgeTR = v3_mix(v3(0.36f, 0.98f, 0.82f), v3(0.86f, 0.76f, 0.96f), smoothstepf(0.75f, 0.98f, v));
                base = v3_add(base, evalSilkPleat(u - spineTR1, edgeTR, v3(0.22f, 0.78f, 0.76f), 0.105f, 0.80f * fadeTR));
                base = v3_add(base, evalSilkPleat(u - spineTR2, v3(0.68f, 0.96f, 0.88f), v3(0.32f, 0.72f, 0.86f), 0.08f, 0.58f * fadeTR));
            }

            // (c) 右下主欧根纱：暖金香槟琥珀 × 梦幻紫罗兰多层波浪丝褶（从底部中右柔顺蜿蜒至右侧中段）
            {
                float sU = clampf((u - 0.40f) / 0.62f, 0.0f, 1.0f);
                float spineB1 = -0.02f + 0.48f * powf(sU, 1.18f) + 0.044f * sinf(u * 8.2f + 0.6f);
                float spineB2 = -0.08f + 0.38f * powf(sU, 1.12f) + 0.048f * cosf(u * 7.0f + 1.5f);
                float spineB3 =  0.04f + 0.54f * powf(sU, 1.28f) + 0.038f * sinf(u * 9.0f + 2.4f);
                float fadeB = smoothstepf(0.38f, 0.49f, u);

                Vec3 warmGold = v3(1.00f, 0.78f, 0.50f);
                Vec3 warmBody = v3(0.88f, 0.52f, 0.58f);
                Vec3 violetEdge = v3(0.76f, 0.50f, 0.98f);
                Vec3 violetBody = v3(0.46f, 0.24f, 0.78f);

                base = v3_add(base, evalSilkPleat(spineB1 - v, warmGold, warmBody, 0.135f, 0.90f * fadeB));
                base = v3_add(base, evalSilkPleat(spineB2 - v, v3(1.00f, 0.84f, 0.62f), warmBody, 0.10f, 0.72f * fadeB));
                base = v3_add(base, evalSilkPleat(spineB3 - v, violetEdge, violetBody, 0.115f, 0.78f * fadeB * smoothstepf(0.52f, 0.74f, u)));
            }

            bgBuf[py * N + px] = v3(clampf(base.r, 0.0f, 1.0f),
                                    clampf(base.g, 0.0f, 1.0f),
                                    clampf(base.b, 0.0f, 1.0f));
        }
    });
}

static inline float evalThinOrbit(float u, float v, float cx, float cy,
                                  float rx, float ry, float deg, float zScale, float *outZ) {
    float rad = deg * (float)(M_PI / 180.0);
    float c = cosf(rad), s = sinf(rad);
    float dx = u - cx, dy = v - cy;
    float lx =  dx * c + dy * s;
    float ly = -dx * s + dy * c;
    float th = atan2f(ly / ry, lx / rx);
    *outZ = sinf(th + 0.35f) * zScale;
    return hypotf(lx - rx * cosf(th), ly - ry * sinf(th));
}

typedef struct {
    float dist;
    float signedDist;
    float z;
    float t;
    float nx, ny;
    Vec3 bodyTint;
    Vec3 causticA;
    Vec3 causticB;
} TubeHit;

// 对单层 3D 透明宝石水晶圆管着色：通透深邃宝石芯 + 彩色内色散丝带 + 锐利白亮棚拍镜面高光（绝不泛白发灰）
static Vec3 shadeJewelCrystalTube(Vec3 behindCol, const Vec3 *bgBuf, int N,
                                  float u, float v, const TubeHit *hit, float tubeR) {
    float q = clampf(hit->signedDist / tubeR, -0.999f, 0.999f);
    float absQ = fabsf(q);
    float nz = sqrtf(fmaxf(0.001f, 1.0f - q * q));
    float nx = q * hit->nx;
    float ny = q * hit->ny;

    // 1. 背景与下层水晶管的真实柱面透镜折射
    float refr = 0.028f * (0.8f + 0.8f * absQ * absQ);
    int rx = (int)clampf((u - nx * refr) * (float)N, 0.0f, (float)(N - 1));
    int ry = (int)clampf((v - ny * refr) * (float)N, 0.0f, (float)(N - 1));
    Vec3 refrBg = bgBuf[ry * N + rx];
    Vec3 through = v3_mix(refrBg, behindCol, 0.66f);

    // 2. 深邃通透水晶吸收与全反射深色内壁（还原图2玻璃管内部浓郁深蓝/深青/深琥珀层次）
    Vec3 absorb = v3_mix(v3(0.92f, 0.94f, 0.98f), hit->bodyTint, 0.62f + 0.26f * absQ);
    Vec3 glass = v3(through.r * absorb.r, through.g * absorb.g, through.b * absorb.b);

    // 内侧深色折射暗环 (|q| ~ 0.62..0.84) 强化厚壁圆管立体体积感
    float darkBand = expf(-powf(absQ - 0.72f, 2.0f) * 34.0f);
    Vec3 deepJewel = v3_scale(hit->bodyTint, 0.20f);
    glass = v3_mix(glass, deepJewel, darkBand * 0.68f);

    // 3. 管内流动双色棱镜色散丝带 (Chromatic Dispersion Ribbons)
    float wave1 = 0.38f * sinf(hit->t * 5.0f + 0.8f);
    float wave2 = -0.34f * cosf(hit->t * 4.0f - 0.5f);
    float ribbonA = expf(-powf(q - wave1, 2.0f) * 28.0f);
    float ribbonB = expf(-powf(q - wave2, 2.0f) * 32.0f);
    glass = v3_add(glass, v3_scale(hit->causticA, ribbonA * 0.34f));
    glass = v3_add(glass, v3_scale(hit->causticB, ribbonB * 0.28f));

    // 4. 锐利清透菲涅尔发光边缘 (|q| ~ 0.93)
    float fresnel = expf(-powf(absQ - 0.925f, 2.0f) * 185.0f);
    Vec3 rimCol = v3_mix(hit->causticA, v3(0.96f, 0.98f, 1.00f), 0.45f);
    glass = v3_add(glass, v3_scale(rimCol, fresnel * 0.78f));

    // 5. 棚拍锐利高光条与顶部耀斑（窄而通透，保持玻璃清澈感）
    float lightFacing = fmaxf(0.0f, -hit->nx * 0.32f + hit->ny * 0.68f + 0.32f);
    float stripMain = expf(-powf(q + 0.54f, 2.0f) * 145.0f) * (0.35f + 0.65f * lightFacing);
    float stripOpposite = expf(-powf(q - 0.64f, 2.0f) * 175.0f) * 0.40f;

    float Hx = -0.20f, Hy = 0.48f, Hz = 0.854f;
    float ndoth = fmaxf(0.0f, nx * Hx + ny * Hy + nz * Hz);
    float sunGlint = powf(ndoth, 140.0f) * 1.10f + powf(ndoth, 32.0f) * 0.16f;

    glass = v3_add(glass, v3_scale(v3(1.0f, 1.0f, 1.0f), stripMain * 0.72f + sunGlint));
    glass = v3_add(glass, v3_scale(hit->causticA, stripOpposite));

    // 超平滑亚像素抗锯齿边缘
    float cov = 1.0f - smoothstepf(0.945f, 1.0f, absQ);
    return v3_mix(behindCol,
                  v3(clampf(glass.r, 0.0f, 1.0f), clampf(glass.g, 0.0f, 1.0f), clampf(glass.b, 0.0f, 1.0f)),
                  cov);
}

static NSBitmapImageRep *buildMasterArtworkRep(void) {
    const int N = 1024;
    Vec3 *bgBuf = (Vec3 *)calloc((size_t)(N * N), sizeof(Vec3));
    Vec3 *finalBuf = (Vec3 *)calloc((size_t)(N * N), sizeof(Vec3));
    KnotVertex *verts = (KnotVertex *)calloc(KNOT_SEGS + 1, sizeof(KnotVertex));

    buildClassicalTrefoil(verts);
    renderBackdropAndOrganza(bgBuf, N);

    const float tubeR = 0.0435f; // 饱满圆润水晶圆管半径 (~44.5px)

    typedef struct { float x, y, arm; Vec3 col; } StarSpec;
    const StarSpec stars[] = {
        { 0.678f, 0.728f, 0.027f, {1.00f, 0.84f, 0.68f} },
        { 0.282f, 0.645f, 0.016f, {1.00f, 0.80f, 0.64f} },
        { 0.190f, 0.482f, 0.020f, {0.88f, 0.96f, 1.00f} },
        { 0.495f, 0.232f, 0.019f, {1.00f, 0.84f, 0.72f} },
        { 0.640f, 0.392f, 0.015f, {1.00f, 0.86f, 0.66f} },
        { 0.306f, 0.678f, 0.009f, {0.96f, 0.92f, 1.00f} },
        { 0.224f, 0.462f, 0.008f, {0.88f, 0.95f, 1.00f} },
    };
    const int starCount = (int)(sizeof(stars) / sizeof(stars[0]));
    const StarSpec *starPtr = stars;

    typedef struct { float x, y, r; Vec3 col; float a; } DustSpec;
    DustSpec dusts[60];
    for (int d = 0; d < 60; d++) {
        float a = (float)d * 2.39996f;
        float rad = 0.18f + 0.18f * fmodf((float)d * 0.317f, 1.0f);
        float tilt = 0.48f;
        float lx = cosf(a) * rad * 1.16f;
        float ly = sinf(a) * rad * 0.66f;
        dusts[d].x = 0.496f + lx * cosf(tilt) - ly * sinf(tilt);
        dusts[d].y = 0.482f + lx * sinf(tilt) + ly * cosf(tilt);
        dusts[d].r = (d % 6 == 0) ? 0.0042f : (0.0018f + (d % 3) * 0.0007f);
        dusts[d].col = (d % 3 == 0) ? v3(1.00f, 0.84f, 0.70f)
                     : (d % 3 == 1) ? v3(0.72f, 0.92f, 1.00f)
                                    : v3(0.92f, 0.84f, 1.00f);
        dusts[d].a = (d % 6 == 0) ? 0.90f : 0.64f;
    }
    const DustSpec *dustPtr = dusts;

    // 多核并行逐像素精确胶囊段解析求交（零空间分块，彻底消除任何方格伪影）
    dispatch_apply(N, dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^(size_t py) {
        float v = ((float)py + 0.5f) / (float)N;
        BOOL inKnotY = (v > 0.12f && v < 0.86f);

        for (int px = 0; px < N; px++) {
            float u = ((float)px + 0.5f) / (float)N;
            Vec3 col = bgBuf[py * N + px];

            // 两条纤细明亮双倾角星轨椭圆（如发丝般锐利优雅）
            float zOrb1 = 0.0f, zOrb2 = 0.0f;
            float dOrb1 = evalThinOrbit(u, v, 0.495f, 0.488f, 0.338f, 0.114f, 22.0f, -0.80f, &zOrb1);
            float dOrb2 = evalThinOrbit(u, v, 0.498f, 0.478f, 0.296f, 0.094f, 42.0f,  0.80f, &zOrb2);

            TubeHit hits[3];
            int hitSegIdx[3] = { -999, -999, -999 };
            int hitCount = 0;
            float minDistAny = 1e9f;
            Vec3 nearCaustic = v3(0.55f, 0.72f, 1.00f);

            if (inKnotY && u > 0.14f && u < 0.86f) {
                // 先找全局连续局部极小距离段（三叶结最多 2 条管在同一点交叠）
                float segDist[KNOT_SEGS];
                float segAlpha[KNOT_SEGS];
                for (int i = 0; i < KNOT_SEGS; i++) {
                    float ax = verts[i].x, ay = verts[i].y;
                    float bx = verts[i + 1].x, by = verts[i + 1].y;
                    float abx = bx - ax, aby = by - ay;
                    float apx = u - ax, apy = v - ay;
                    float denom = abx * abx + aby * aby + 1e-12f;
                    float h = clampf((apx * abx + apy * aby) / denom, 0.0f, 1.0f);
                    float dx = apx - abx * h;
                    float dy = apy - aby * h;
                    float d = sqrtf(dx * dx + dy * dy);
                    segDist[i] = d;
                    segAlpha[i] = h;
                    if (d < minDistAny) {
                        minDistAny = d;
                        nearCaustic = verts[i].causticA;
                    }
                }

                // 提取所有距离 < tubeR 的独立连续曲线波谷分支
                for (int i = 0; i < KNOT_SEGS; i++) {
                    float d = segDist[i];
                    if (d >= tubeR) continue;
                    int prev = (i - 1 + KNOT_SEGS) % KNOT_SEGS;
                    int next = (i + 1) % KNOT_SEGS;
                    if (d <= segDist[prev] && d < segDist[next]) {
                        // 检查是否与已记录峰值过近（防数值双峰）
                        BOOL duplicate = NO;
                        for (int k = 0; k < hitCount; k++) {
                            int diff = abs(i - hitSegIdx[k]);
                            if (diff > KNOT_SEGS / 2) diff = KNOT_SEGS - diff;
                            if (diff < 24) {
                                duplicate = YES;
                                if (d < hits[k].dist) {
                                    float h = segAlpha[i];
                                    float cxSeg = verts[i].x + (verts[i + 1].x - verts[i].x) * h;
                                    float cySeg = verts[i].y + (verts[i + 1].y - verts[i].y) * h;
                                    float nx = verts[i].nx + (verts[i + 1].nx - verts[i].nx) * h;
                                    float ny = verts[i].ny + (verts[i + 1].ny - verts[i].ny) * h;
                                    float nLen = hypotf(nx, ny) + 1e-6f;
                                    nx /= nLen; ny /= nLen;
                                    float sgn = ((u - cxSeg) * nx + (v - cySeg) * ny) >= 0.0f ? 1.0f : -1.0f;
                                    hits[k].dist = d;
                                    hits[k].signedDist = sgn * d;
                                    hits[k].z = verts[i].z + (verts[i + 1].z - verts[i].z) * h;
                                    hits[k].t = verts[i].t + (verts[i + 1].t - verts[i].t) * h;
                                    hits[k].nx = nx;
                                    hits[k].ny = ny;
                                    hits[k].bodyTint = v3_mix(verts[i].bodyTint, verts[i + 1].bodyTint, h);
                                    hits[k].causticA = v3_mix(verts[i].causticA, verts[i + 1].causticA, h);
                                    hits[k].causticB = v3_mix(verts[i].causticB, verts[i + 1].causticB, h);
                                    hitSegIdx[k] = i;
                                }
                                break;
                            }
                        }
                        if (!duplicate && hitCount < 3) {
                            float h = segAlpha[i];
                            float cxSeg = verts[i].x + (verts[i + 1].x - verts[i].x) * h;
                            float cySeg = verts[i].y + (verts[i + 1].y - verts[i].y) * h;
                            float nx = verts[i].nx + (verts[i + 1].nx - verts[i].nx) * h;
                            float ny = verts[i].ny + (verts[i + 1].ny - verts[i].ny) * h;
                            float nLen = hypotf(nx, ny) + 1e-6f;
                            nx /= nLen; ny /= nLen;
                            float sgn = ((u - cxSeg) * nx + (v - cySeg) * ny) >= 0.0f ? 1.0f : -1.0f;
                            TubeHit th;
                            th.dist = d;
                            th.signedDist = sgn * d;
                            th.z = verts[i].z + (verts[i + 1].z - verts[i].z) * h;
                            th.t = verts[i].t + (verts[i + 1].t - verts[i].t) * h;
                            th.nx = nx;
                            th.ny = ny;
                            th.bodyTint = v3_mix(verts[i].bodyTint, verts[i + 1].bodyTint, h);
                            th.causticA = v3_mix(verts[i].causticA, verts[i + 1].causticA, h);
                            th.causticB = v3_mix(verts[i].causticB, verts[i + 1].causticB, h);
                            hitSegIdx[hitCount] = i;
                            hits[hitCount++] = th;
                        }
                    }
                }
            }

            // 极轻柔水晶边缘环境微光（克制不过曝，保持背景通透对比）
            if (minDistAny < tubeR + 0.024f) {
                float g = expf(-powf(fmaxf(0.0f, minDistAny - tubeR * 0.92f) / 0.013f, 2.0f));
                col = v3_add(col, v3_scale(nearCaustic, g * 0.11f));
            }

            // 按 3D Z 深度从后往前排序
            for (int a = 0; a < hitCount - 1; a++) {
                for (int b = a + 1; b < hitCount; b++) {
                    if (hits[a].z > hits[b].z) {
                        TubeHit tmp = hits[a];
                        hits[a] = hits[b];
                        hits[b] = tmp;
                    }
                }
            }

            float frontZ = (hitCount > 0) ? hits[hitCount - 1].z : -99.0f;

            // 后层纤细星轨（约 1.4px 锐利细丝 + 轻柔微晕）
            if (dOrb1 < 0.010f && zOrb1 < frontZ) {
                float core = expf(-powf(dOrb1 / 0.00115f, 2.0f));
                float bloom = expf(-powf(dOrb1 / 0.0042f, 2.0f));
                col = v3_add(col, v3_scale(v3(0.86f, 0.80f, 1.00f), bloom * 0.18f + core * 0.82f));
            }
            if (dOrb2 < 0.010f && zOrb2 < frontZ) {
                float core = expf(-powf(dOrb2 / 0.00105f, 2.0f));
                float bloom = expf(-powf(dOrb2 / 0.0038f, 2.0f));
                col = v3_add(col, v3_scale(v3(0.82f, 0.92f, 1.00f), bloom * 0.16f + core * 0.78f));
            }

            // 逐层从后往前折射合成 3D 透明水晶圆管
            for (int m = 0; m < hitCount; m++) {
                col = shadeJewelCrystalTube(col, bgBuf, N, u, v, &hits[m], tubeR);
            }

            // 前层跨越在水晶三叶结前方的纤细白亮星轨丝线
            if (dOrb1 < 0.010f && zOrb1 >= frontZ) {
                float core = expf(-powf(dOrb1 / 0.00118f, 2.0f));
                float bloom = expf(-powf(dOrb1 / 0.0045f, 2.0f));
                col = v3_add(col, v3_scale(v3(0.95f, 0.90f, 1.00f), bloom * 0.22f + core * 0.94f));
            }
            if (dOrb2 < 0.010f && zOrb2 >= frontZ) {
                float core = expf(-powf(dOrb2 / 0.00110f, 2.0f));
                float bloom = expf(-powf(dOrb2 / 0.0042f, 2.0f));
                col = v3_add(col, v3_scale(v3(0.94f, 0.97f, 1.00f), bloom * 0.20f + core * 0.92f));
            }

            // 璀璨星尘微粒
            for (int d = 0; d < 60; d++) {
                float dd = hypotf(u - dustPtr[d].x, v - dustPtr[d].y);
                if (dd < dustPtr[d].r * 4.0f) {
                    float core = 1.0f - smoothstepf(dustPtr[d].r * 0.42f, dustPtr[d].r * 1.12f, dd);
                    float glow = expf(-powf(dd / (dustPtr[d].r * 2.2f), 2.0f)) * 0.40f;
                    col = v3_add(col, v3_scale(dustPtr[d].col, (core + glow) * dustPtr[d].a));
                }
            }

            // 精雕凹弧四芒星芒
            for (int s = 0; s < starCount; s++) {
                float dx = fabsf(u - starPtr[s].x);
                float dy = fabsf(v - starPtr[s].y);
                float arm = starPtr[s].arm;
                if (dx < arm * 1.25f && dy < arm * 1.25f) {
                    float field = powf(dx / arm + 1e-5f, 0.54f) + powf(dy / arm + 1e-5f, 0.54f);
                    float starBody = 1.0f - smoothstepf(0.84f, 1.03f, field);
                    float starHalo = expf(-(dx * dx + dy * dy) / (arm * arm * 0.30f)) * 0.42f;
                    col = v3_add(col, v3_scale(starPtr[s].col, starHalo));
                    col = v3_mix(col, v3(1.0f, 0.98f, 0.95f), starBody * 0.96f);
                }
            }

            finalBuf[py * N + px] = v3(clampf(col.r, 0.0f, 1.0f),
                                       clampf(col.g, 0.0f, 1.0f),
                                       clampf(col.b, 0.0f, 1.0f));
        }
    });

    NSBitmapImageRep *masterRep = [[NSBitmapImageRep alloc]
        initWithBitmapDataPlanes:NULL
                      pixelsWide:N
                      pixelsHigh:N
                   bitsPerSample:8
                 samplesPerPixel:4
                        hasAlpha:YES
                        isPlanar:NO
                  colorSpaceName:NSDeviceRGBColorSpace
                     bytesPerRow:N * 4
                    bitsPerPixel:32];

    unsigned char *dst = [masterRep bitmapData];
    for (int py = 0; py < N; py++) {
        int srcRow = N - 1 - py;
        for (int px = 0; px < N; px++) {
            Vec3 c = finalBuf[srcRow * N + px];
            size_t off = (size_t)(py * N + px) * 4;
            dst[off + 0] = (unsigned char)lrintf(c.r * 255.0f);
            dst[off + 1] = (unsigned char)lrintf(c.g * 255.0f);
            dst[off + 2] = (unsigned char)lrintf(c.b * 255.0f);
            dst[off + 3] = 255;
        }
    }

    free(verts);
    free(bgBuf);
    free(finalBuf);
    return masterRep;
}

static void renderIconPNGFromMaster(NSImage *masterImg, NSString *outPath, int pxSize, int ptSize) {
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

    NSRect iconRect = NSMakeRect(64, 64, 896, 896);
    NSBezierPath *squircle = [NSBezierPath bezierPathWithRoundedRect:iconRect xRadius:204 yRadius:204];

    [NSGraphicsContext saveGraphicsState];
    NSShadow *dropShadow = [[NSShadow alloc] init];
    dropShadow.shadowOffset = NSMakeSize(0, -14.0);
    dropShadow.shadowBlurRadius = 30.0;
    dropShadow.shadowColor = [NSColor colorWithSRGBRed:0.05 green:0.04 blue:0.18 alpha:0.30];
    [dropShadow set];
    [[NSColor colorWithSRGBRed:0.05 green:0.06 blue:0.20 alpha:1.0] setFill];
    [squircle fill];
    [NSGraphicsContext restoreGraphicsState];

    [NSGraphicsContext saveGraphicsState];
    [squircle addClip];
    [masterImg drawInRect:iconRect
                 fromRect:NSMakeRect(0, 0, 1024, 1024)
                operation:NSCompositingOperationSourceOver
                 fraction:1.0];
    [NSGraphicsContext restoreGraphicsState];

    NSBezierPath *rim = [NSBezierPath bezierPathWithRoundedRect:NSInsetRect(iconRect, 0.8, 0.8) xRadius:203.2 yRadius:203.2];
    [rim setLineWidth:1.4];
    [[NSColor colorWithCalibratedWhite:1.0 alpha:0.14] setStroke];
    [rim stroke];

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
        NSBitmapImageRep *masterRep = buildMasterArtworkRep();
        NSImage *masterImg = [[NSImage alloc] initWithSize:NSMakeSize(1024, 1024)];
        [masterImg addRepresentation:masterRep];

        NSString *iconsetDir = [NSString stringWithUTF8String:argv[1]];
        int sizes[5] = {16, 32, 128, 256, 512};
        for (int i = 0; i < 5; i++) {
            int s = sizes[i];
            NSString *p1 = [iconsetDir stringByAppendingPathComponent:[NSString stringWithFormat:@"icon_%dx%d.png", s, s]];
            NSString *p2 = [iconsetDir stringByAppendingPathComponent:[NSString stringWithFormat:@"icon_%dx%d@2x.png", s, s]];
            renderIconPNGFromMaster(masterImg, p1, s, s);
            renderIconPNGFromMaster(masterImg, p2, s * 2, s);
        }
        for (int a = 2; a < argc; a++) {
            NSString *arg = [NSString stringWithUTF8String:argv[a]];
            if ([arg isEqualToString:@"--icns"] && a + 1 < argc) {
                NSString *icnsPath = [NSString stringWithUTF8String:argv[++a]];
                if (!writeIcnsFile(iconsetDir, icnsPath)) return 2;
            } else if ([arg isEqualToString:@"--web-icon"] && a + 1 < argc) {
                NSString *webPath = [NSString stringWithUTF8String:argv[++a]];
                const int webPx = 256;
                NSBitmapImageRep *webRep = [[NSBitmapImageRep alloc]
                    initWithBitmapDataPlanes:NULL
                                  pixelsWide:webPx
                                  pixelsHigh:webPx
                               bitsPerSample:8
                             samplesPerPixel:4
                                    hasAlpha:YES
                                    isPlanar:NO
                              colorSpaceName:NSDeviceRGBColorSpace
                                 bytesPerRow:0
                                bitsPerPixel:0];
                [webRep setSize:NSMakeSize(webPx, webPx)];
                [NSGraphicsContext saveGraphicsState];
                NSGraphicsContext *wctx = [NSGraphicsContext graphicsContextWithBitmapImageRep:webRep];
                wctx.imageInterpolation = NSImageInterpolationHigh;
                wctx.shouldAntialias = YES;
                [NSGraphicsContext setCurrentContext:wctx];
                NSRect fullRect = NSMakeRect(0, 0, webPx, webPx);
                NSBezierPath *sq = [NSBezierPath bezierPathWithRoundedRect:fullRect xRadius:58.0 yRadius:58.0];
                [sq addClip];
                [masterImg drawInRect:fullRect
                             fromRect:NSMakeRect(0, 0, 1024, 1024)
                            operation:NSCompositingOperationSourceOver
                             fraction:1.0];
                NSBezierPath *rim = [NSBezierPath bezierPathWithRoundedRect:NSInsetRect(fullRect, 0.75, 0.75) xRadius:57.25 yRadius:57.25];
                [rim setLineWidth:1.2];
                [[NSColor colorWithCalibratedWhite:1.0 alpha:0.20] setStroke];
                [rim stroke];
                [NSGraphicsContext restoreGraphicsState];
                NSData *wData = [webRep representationUsingType:NSBitmapImageFileTypePNG properties:@{}];
                [wData writeToFile:webPath atomically:YES];
            } else {
                renderIconPNGFromMaster(masterImg, arg, 1024, 1024);
            }
        }
    }
    return 0;
}
