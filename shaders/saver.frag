// System 1 — OLED screensaver. Pure black; the only lit pixels move.
precision highp float;

uniform vec2 uRes;
uniform float uTime;
uniform vec3 uClock;   // h, m, s
uniform float uSeed;
uniform float uBirdAspect;
uniform sampler2D uBird;
uniform sampler2D uText;
uniform sampler2D uDigits;

const float PX = 2.0;
const vec3 RED = vec3(0.878, 0.0, 0.0);
const int TRAIL = 22;

float bayer2(vec2 a) { a = floor(a); return fract(dot(a, vec2(0.5, a.y * 0.75))); }
float bayer4(vec2 a) { return bayer2(0.5 * a) * 0.25 + bayer2(a); }
float bayer8(vec2 a) { return bayer4(0.5 * a) * 0.25 + bayer2(a); }
float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float aspect;
float bh;   // bird height in screen heights

// The flight path: a slow Lissajous figure that covers the whole screen
vec2 path(float t) {
    return vec2(0.40 * aspect * sin(t * 0.071 + uSeed),
                0.5 + 0.33 * sin(t * 0.113 + 1.3 + uSeed * 0.5));
}

float birdAt(vec2 q, float t) {
    vec2 c = path(t);
    float dir = cos(t * 0.071 + uSeed) >= 0.0 ? 1.0 : -1.0;   // face the way it flies
    float flap = 0.8 + 0.2 * sin(t * 2.2);
    float bw = bh * uBirdAspect;
    vec2 l = vec2(dir * (q.x - c.x) / bw + 0.5, 0.5 - (q.y - c.y) / (bh * flap));
    if (l.x < 0.0 || l.x > 1.0 || l.y < 0.0 || l.y > 1.0) return 0.0;
    return smoothstep(0.3, 0.7, texture2D(uBird, l).r);
}

float digit(float d, vec2 l) {   // d: 0-9, 10 = colon; l in 0..1 within the cell
    if (l.x < 0.0 || l.x > 1.0 || l.y < 0.0 || l.y > 1.0) return 0.0;
    return texture2D(uDigits, vec2((d + l.x) / 11.0, l.y)).r;
}

void main() {
    aspect = uRes.x / uRes.y;
    bh = aspect < 1.0 ? 0.14 : 0.24;
    vec2 cell = floor(gl_FragCoord.xy / PX);
    vec2 uv = cell * PX / uRes;
    vec2 q = vec2((uv.x - 0.5) * aspect, uv.y);
    float t = uTime + uSeed * 53.0;

    float ink = 0.0, red = 0.0;

    // the bird in red, with a white dither trail that thins out behind it
    red += birdAt(q, t) * (0.7 + 0.3 * sin(q.x * 9.0 - t * 1.5));
    for (int i = 1; i <= TRAIL; i++) {
        float k = float(i);
        float b = birdAt(q, t - k * 0.55);
        if (b > 0.0) {
            float fade = 1.0 - k / float(TRAIL + 1);
            ink = max(ink, b * fade * fade * 0.55);
        }
    }

    // stars drifting slowly sideways
    vec2 sc = floor((q + vec2(t * 0.004, 0.0)) * uRes.y / (PX * 3.0));
    float s = hash(sc + uSeed);
    ink += step(0.998, s) * (0.4 + 0.4 * sin(t * (0.5 + s * 2.0) + s * 50.0));

    // HH:MM in VT323, bouncing very slowly around the screen
    {
        float dh = 0.07;                      // digit height
        float dw = dh * 0.5;
        float w = dw * 5.0;
        vec2 room = vec2(aspect - w, 1.0 - dh) * 0.5 - 0.04;
        vec2 tri = abs(fract(vec2(t * 0.0031, t * 0.0047) + uSeed * 0.1) * 2.0 - 1.0) * 2.0 - 1.0;
        vec2 o = vec2(tri.x * room.x - w * 0.5, 0.5 + tri.y * room.y - dh * 0.5);
        vec2 l = (q - o) / vec2(dw, dh);
        if (l.x >= 0.0 && l.x < 5.0 && l.y >= 0.0 && l.y < 1.0) {
            float slot = floor(l.x);
            float d = slot < 0.5 ? floor(uClock.x / 10.0) : slot < 1.5 ? mod(uClock.x, 10.0)
                    : slot < 2.5 ? 10.0 : slot < 3.5 ? floor(uClock.y / 10.0) : mod(uClock.y, 10.0);
            float c = digit(d, vec2(fract(l.x), 1.0 - l.y));
            // the colon blinks
            if (slot > 1.5 && slot < 2.5) c *= step(0.5, fract(uClock.z * 0.5));
            ink += c * 0.5;
        }
    }

    // 折り紙, faint, drifting up the right-hand side
    {
        float ch = 0.035, colH = ch * 6.0;
        float y = fract(t * 0.004) * 1.6 - 0.3;
        vec2 l = vec2((q.x - (aspect * 0.5 - 0.07)) / ch + 0.5, (y - q.y) / colH);
        if (l.x > 0.0 && l.x < 1.0 && l.y > 0.0 && l.y < 1.0)
            ink += texture2D(uText, vec2((4.0 + l.x) / 8.0, l.y)).r * 0.35;
    }

    float th = bayer8(cell) + 0.5 / 64.0;
    vec3 col = vec3(0.0);
    if (th < clamp(ink, 0.0, 1.0)) col = vec3(1.0);
    if (th < clamp(red, 0.0, 1.0)) col = RED;
    gl_FragColor = vec4(col, 1.0);
}
