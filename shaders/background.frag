// System 1 — animated background.
// Everything is computed as "ink coverage" (white ink in dark mode, black in
// light mode) plus "red coverage", then ordered-dithered to three colours.
// Dark mode keeps coverage low so most of the OLED stays truly off.
precision highp float;

uniform vec2 uRes;
uniform float uTime;   // seconds since start
uniform float uHour;   // local time, 0..24
uniform vec2 uSun;     // today's sunrise, sunset (local hours)
uniform float uDark;   // 1 dark, 0 light (animated during switches)
uniform float uSeed;   // differs per output
uniform float uBirdAspect;
uniform sampler2D uBird;
uniform sampler2D uText;

const float PX = 2.0;              // size of one 1-bit pixel
const vec3 RED = vec3(0.878, 0.0, 0.0);
const float HORIZON = 0.0;

float bayer2(vec2 a) { a = floor(a); return fract(dot(a, vec2(0.5, a.y * 0.75))); }
float bayer4(vec2 a) { return bayer2(0.5 * a) * 0.25 + bayer2(a); }
float bayer8(vec2 a) { return bayer4(0.5 * a) * 0.25 + bayer2(a); }

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 5; i++) { v += a * noise(p); p = p * 2.03 + 17.0; a *= 0.5; }
    return v;
}

// phrase lengths in the caption atlas (see build-assets.sh)
float phraseLen(float i) {
    if (i < 0.5) return 4.0; if (i < 1.5) return 5.0; if (i < 2.5) return 3.0; if (i < 3.5) return 4.0;
    if (i < 4.5) return 3.0; if (i < 5.5) return 2.0; if (i < 6.5) return 4.0; return 1.0;
}
// local (0..1, 0..1 top-down) inside one atlas column
float textAt(float col, vec2 l) {
    if (l.x < 0.0 || l.x > 1.0 || l.y < 0.0 || l.y > 1.0) return 0.0;
    return texture2D(uText, vec2((col + l.x) / 8.0, l.y)).r;
}

float birdAt(vec2 l) {   // l: 0..1 across the logo, y top-down
    if (l.x < 0.0 || l.x > 1.0 || l.y < 0.0 || l.y > 1.0) return 0.0;
    return texture2D(uBird, l).r;
}

void main() {
    // OLED pixel shift: the whole scene orbits a few pixels every ~10 minutes
    vec2 shift = vec2(cos(uTime * 0.0105), sin(uTime * 0.0137)) * 6.0;
    vec2 cell = floor((gl_FragCoord.xy + shift) / PX);
    vec2 uv = cell * PX / uRes;                 // 0..1, y up
    float aspect = uRes.x / uRes.y;
    vec2 q = vec2((uv.x - 0.5) * aspect, uv.y);  // x centred, in screen heights
    float t = uTime + uSeed * 37.0;
    float h = uHour;

    float rise = uSun.x, set = uSun.y;
    float day = smoothstep(rise - 0.6, rise + 1.0, h) * (1.0 - smoothstep(set - 0.8, set + 0.8, h));
    float dusk = exp(-pow((h - set) / 0.9, 2.0)) + exp(-pow((h - rise) / 0.8, 2.0));
    float night = 1.0 - day;
    // dark mode spends far less light on the same scene
    float budget = mix(1.0, 0.42, uDark);

    float ink = 0.0, red = 0.0, birdHere = 0.0;

    // ── Sky: slow banded clouds, thinner at night ──
    if (uv.y > HORIZON) {
        float above = uv.y - HORIZON;
        vec2 cp = vec2(q.x * 1.6 + t * 0.006, above * 4.5);
        float c = fbm(cp + vec2(uSeed, 0.0)) + 0.18 * fbm(cp * 3.0 - t * 0.01);
        float cloud = smoothstep(0.58, 0.82, c) * mix(0.35, 0.55, day);
        // clouds quantised into bands, like a MacPaint fill
        cloud = floor(cloud * 4.0) / 4.0;
        ink += cloud * mix(0.45, 1.0, day);
        // haze hugging the horizon, warmer (red) around sunrise and sunset
        float haze = exp(-above * 40.0);
        ink += haze * 0.18;
        red += exp(-above * 22.0) * 0.22 * dusk;
    }

    // ── Sun (day) / moon (night), placed by the real time ──
    {
        float a = clamp((h - rise) / (set - rise), 0.0, 1.0);
        float na = mod(h - set + 24.0, 24.0) / (24.0 - (set - rise));   // sunset → sunrise
        vec2 sun = vec2(mix(-0.55, 0.55, a) * aspect * 0.8, HORIZON + 0.52 * sin(3.14159 * a));
        vec2 moon = vec2(mix(-0.55, 0.55, clamp(na, 0.0, 1.0)) * aspect * 0.8, HORIZON + 0.5 * sin(3.14159 * clamp(na, 0.0, 1.0)));
        float rs = 0.105;
        float ds = length(q - sun);
        if (day > 0.0 && ds < rs && uv.y > HORIZON) {
            // retro-futurist sun: horizontal cuts that widen towards the bottom
            float yy = (q.y - sun.y) / rs;              // -1 bottom .. 1 top
            float band = fract(yy * 4.0 - t * 0.012);
            float cut = yy < 0.15 ? step(band, mix(0.15, 0.55, clamp(-yy, 0.0, 1.0))) : 0.0;
            float shade = mix(1.0, 0.6, ds / rs);
            red += (1.0 - cut) * shade * day * mix(1.0, 0.55, uDark);
        }
        if (night > 0.0 && na <= 1.0) {
            float rm = 0.075;
            float d1 = length(q - moon), d2 = length(q - moon - vec2(0.03, 0.012));
            float crescent = step(d1, rm) * smoothstep(rm * 0.92, rm * 1.02, d2);
            ink += crescent * night * 0.85 * (0.7 + 0.3 * (1.0 - d1 / rm));
        }
    }

    // ── Stars: sparse, twinkling, slowly wheeling around a point off screen ──
    if (uv.y > HORIZON + 0.04 && night > 0.01) {
        vec2 pole = vec2(0.2 * aspect, 1.25);
        vec2 r = q - pole;
        float ang = t * 0.0009;
        r = mat2(cos(ang), -sin(ang), sin(ang), cos(ang)) * r;
        // stars sit at cell centres in the rotating sky and are drawn as
        // round dots, so they glide instead of popping between cells
        float cs = PX * 6.0 / uRes.y;
        vec2 sc = floor(r / cs);
        float s = hash(sc + uSeed);
        vec2 off = vec2(hash(sc + 7.1), hash(sc + 3.3)) - 0.5;
        float d = length(r - (sc + 0.5 + off * 0.5) * cs) * uRes.y;
        float twinkle = 0.8 + 0.2 * sin(t * (0.04 + s * 0.08) + s * 40.0);
        ink += step(0.993, s) * step(d, PX * mix(0.8, 1.6, fract(s * 977.0))) * twinkle * night * 2.4;
    }

    // ── The bird: glides across every ~2.5 minutes, flapping slowly ──
    {
        float period = 420.0;
        float k = floor(t / period);
        float p = fract(t / period) * period / 240.0;    // crosses in 4 minutes, then gone
        if (p < 1.0) {
            float bh = 0.12 + 0.03 * hash(vec2(k, 1.0));              // height in screen heights
            float bw = bh * uBirdAspect;
            float span = aspect + bw * 2.0;
            vec2 c = vec2(-aspect * 0.5 - bw + span * p,
                          0.55 + 0.2 * hash(vec2(k, 2.0)) + 0.012 * sin(t * 0.15));
            vec2 l = vec2((q.x - c.x) / bw + 0.5, 0.5 - (q.y - c.y) / bh);
            // solid, undithered, so it doesn't shimmer as it moves
            birdHere = step(0.5, birdAt(l));
        }
    }

    // ── Vertical caption with a hanko seal, fading in and out ──
    {
        float period = 120.0;
        float k = floor(t / period);
        float p = fract(t / period);
        float life = smoothstep(0.0, 0.15, p) * (1.0 - smoothstep(0.6, 0.8, p));
        // every other caption greets the time of day, the rest pick a phrase
        float greet = h < rise - 1.0 ? 3.0 : h < 11.0 ? 0.0 : h < set - 1.0 ? 1.0 : h < set + 1.0 ? 2.0 : 3.0;
        float col = mod(k, 2.0) < 0.5 ? greet : 4.0 + floor(hash(vec2(k, 5.0)) * 2.999);
        float len = phraseLen(col);
        float ch = 0.042;                                  // glyph size in screen heights
        float colH = ch * 6.0;                             // one atlas column is 960/160 = 6 glyph widths tall
        float textH = colH * (8.0 + len * 150.0) / 960.0;
        float side = hash(vec2(k, 3.0)) < 0.5 ? -1.0 : 1.0;
        vec2 top = vec2(side * (aspect * 0.5 - 0.06 - 0.12 * hash(vec2(k, 4.0))), 0.9 - 0.15 * hash(vec2(k, 6.0)));
        vec2 l = vec2((q.x - top.x) / ch + 0.5, (top.y - q.y) / colH);
        ink += textAt(col, l) * life * mix(0.95, 0.75, uDark);
        // seal: a red square with 鳥 knocked out, under the caption
        float sealS = ch * 1.15;
        vec2 sl = (vec2(q.x - top.x, top.y - textH - 0.012 - q.y)) / sealS;
        if (abs(sl.x) < 0.5 && sl.y > 0.0 && sl.y < 1.0) {
            float glyph = textAt(7.0, vec2(sl.x * 0.9 + 0.5, sl.y * 0.9 / 6.0 + 0.005));
            red += (1.0 - step(0.5, glyph)) * life * 0.9;
        }
    }


    ink = clamp(ink * budget, 0.0, 1.0);
    red = clamp(red * mix(1.0, 0.8, uDark), 0.0, 1.0);

    float th = bayer8(cell) + 0.5 / 64.0;
    // mode switch: an ordered dissolve between the two palettes
    float darkHere = step(bayer8(cell + 3.0), uDark - 0.001 + step(0.999, uDark));
    vec3 paper = mix(vec3(1.0), vec3(0.0), darkHere);
    vec3 inkc = mix(vec3(0.0), vec3(1.0), darkHere);

    vec3 col = paper;
    if (th < ink) col = inkc;
    if (th < red || birdHere > 0.0) col = RED;
    gl_FragColor = vec4(col, 1.0);
}
