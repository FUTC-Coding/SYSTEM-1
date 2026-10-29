#version 300 es
// System 1 screen shader: the whole desktop as a 1-bit display. Strong reds
// survive as the one accent colour; everything else becomes black or white
// through an 8x8 ordered dither on 2 px dots. Toggle with SUPER+CTRL+D.
precision highp float;

in vec2 v_texcoord;
uniform sampler2D tex;
out vec4 fragColor;

const float PX = 2.0;
const vec3 RED = vec3(0.878, 0.0, 0.0);

float bayer2(vec2 a) { a = floor(a); return fract(dot(a, vec2(0.5, a.y * 0.75))); }
float bayer4(vec2 a) { return bayer2(0.5 * a) * 0.25 + bayer2(a); }
float bayer8(vec2 a) { return bayer4(0.5 * a) * 0.25 + bayer2(a); }

void main() {
    vec2 size = vec2(textureSize(tex, 0));
    vec2 cell = floor(v_texcoord * size / PX);
    // sample the middle of each 2x2 dot so the dither stays crisp
    vec3 c = texture(tex, (cell + 0.5) * PX / size).rgb;

    float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
    // a touch of contrast so text and UI rules snap to solid black/white
    luma = clamp((luma - 0.5) * 1.25 + 0.5, 0.0, 1.0);
    float redness = clamp((c.r - max(c.g, c.b)) * 1.6, 0.0, 1.0);

    float th = bayer8(cell) + 0.5 / 64.0;
    vec3 col = th < luma ? vec3(1.0) : vec3(0.0);
    if (th < redness) col = RED;
    fragColor = vec4(col, 1.0);
}
