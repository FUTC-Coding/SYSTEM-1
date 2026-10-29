/*
 * system1-bg — the System 1 theme's animated 1-bit background and OLED
 * screensaver. One layer-shell surface per output, drawn with a single
 * GLES2 fragment shader that ends in an ordered dither.
 *
 *   system1-bg                 animated background (bottom layer, no input)
 *   system1-bg --saver         screensaver (overlay layer, exits on input)
 *   system1-bg --snapshot W H dark|light HOUR out.ppm   (SYSTEM1_SCENE=saver for the saver)
 *                              render one background frame to a file
 *
 * The background follows ~/.cache/system1/mode ("dark" or "light"),
 * dissolving between the two. SIGUSR1 pauses/resumes, SIGHUP reloads
 * the shaders.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <math.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <linux/input-event-codes.h>
#include <wayland-client.h>
#include <wayland-egl.h>

#include "wlr-layer-shell-unstable-v1-client-protocol.h"

enum run_mode { MODE_BG, MODE_SAVER, MODE_SNAPSHOT };

struct output {
    struct wl_list link;
    uint32_t name;
    struct wl_output *wl_output;
    struct wl_surface *surface;
    struct zwlr_layer_surface_v1 *layer;
    struct wl_egl_window *egl_window;
    EGLSurface egl_surface;
    int width, height;
    bool configured, frame_ready;
    double next_due;
    float seed;
};

static struct {
    enum run_mode mode;
    struct wl_display *display;
    struct wl_compositor *compositor;
    struct zwlr_layer_shell_v1 *layer_shell;
    struct wl_seat *seat;
    struct wl_keyboard *keyboard;
    struct wl_pointer *pointer;
    struct wl_list outputs;

    EGLDisplay egl_display;
    EGLConfig egl_config;
    EGLContext egl_context;
    bool gl_ready;
    GLuint program, quad, tex_bird, tex_text, tex_digits;
    float bird_aspect;

    bool saver_scene;   // draw saver.frag (the saver, or a snapshot of it)
    double start, fps;
    float dark, dark_target;
    time_t mode_checked;
    struct timespec mode_mtime;
    char shader_dir[512], asset_dir[512], mode_file[512];
} app;

static volatile sig_atomic_t quit_flag, pause_flag, reload_flag;

static double now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec / 1e9;
}

static void die(const char *msg)
{
    fprintf(stderr, "system1-bg: %s\n", msg);
    exit(1);
}

/* ─── Files ─────────────────────────────────────────────── */

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    rewind(f);
    char *buf = malloc(n + 1);
    if (fread(buf, 1, n, f) != (size_t)n) {
        free(buf);
        fclose(f);
        return NULL;
    }
    buf[n] = 0;
    fclose(f);
    return buf;
}

// 8-bit binary PGM (P5) without comments, as written by build-assets.sh
static unsigned char *read_pgm(const char *path, int *w, int *h)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return NULL;
    int maxval;
    if (fscanf(f, "P5 %d %d %d", w, h, &maxval) != 3 || maxval != 255) {
        fclose(f);
        return NULL;
    }
    fgetc(f);
    size_t n = (size_t)*w * *h;
    unsigned char *px = malloc(n);
    if (fread(px, 1, n, f) != n) {
        free(px);
        px = NULL;
    }
    fclose(f);
    return px;
}

static float read_mode_file(void)
{
    char *s = read_file(app.mode_file);
    float dark = 1.0f;
    if (s && strncmp(s, "light", 5) == 0)
        dark = 0.0f;
    free(s);
    return dark;
}

static void poll_mode_file(void)
{
    time_t t = time(NULL);
    if (t == app.mode_checked)
        return;
    app.mode_checked = t;
    struct stat st;
    if (stat(app.mode_file, &st) != 0)
        return;
    if (st.st_mtim.tv_sec == app.mode_mtime.tv_sec && st.st_mtim.tv_nsec == app.mode_mtime.tv_nsec)
        return;
    app.mode_mtime = st.st_mtim;
    app.dark_target = read_mode_file();
}

/* ─── GL ────────────────────────────────────────────────── */

static GLuint compile(GLenum type, const char *src, const char *name)
{
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[4096];
        glGetShaderInfoLog(s, sizeof log, NULL, log);
        fprintf(stderr, "system1-bg: %s:\n%s\n", name, log);
        glDeleteShader(s);
        return 0;
    }
    return s;
}

static const char *VS =
    "attribute vec2 aPos;\n"
    "void main() { gl_Position = vec4(aPos, 0.0, 1.0); }\n";

// Keeps the previous program if the new source does not compile
static void load_program(void)
{
    char path[600];
    snprintf(path, sizeof path, "%s/%s", app.shader_dir, app.saver_scene ? "saver.frag" : "background.frag");
    char *fs_src = read_file(path);
    if (!fs_src) {
        fprintf(stderr, "system1-bg: cannot read %s\n", path);
        return;
    }
    GLuint vs = compile(GL_VERTEX_SHADER, VS, "vertex shader");
    GLuint fs = compile(GL_FRAGMENT_SHADER, fs_src, path);
    free(fs_src);
    if (!vs || !fs)
        return;
    GLuint p = glCreateProgram();
    glAttachShader(p, vs);
    glAttachShader(p, fs);
    glBindAttribLocation(p, 0, "aPos");
    glLinkProgram(p);
    glDeleteShader(vs);
    glDeleteShader(fs);
    GLint ok;
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) {
        fprintf(stderr, "system1-bg: link failed\n");
        glDeleteProgram(p);
        return;
    }
    if (app.program)
        glDeleteProgram(app.program);
    app.program = p;
}

static GLuint load_texture(const char *file, float *aspect)
{
    char path[600];
    snprintf(path, sizeof path, "%s/%s", app.asset_dir, file);
    int w, h;
    unsigned char *px = read_pgm(path, &w, &h);
    if (!px) {
        fprintf(stderr, "system1-bg: cannot read %s (run build-assets.sh)\n", path);
        w = h = 1;
        px = calloc(1, 1);
    }
    if (aspect)
        *aspect = (float)w / h;
    GLuint t;
    glGenTextures(1, &t);
    glBindTexture(GL_TEXTURE_2D, t);
    glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_LUMINANCE, w, h, 0, GL_LUMINANCE, GL_UNSIGNED_BYTE, px);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    free(px);
    return t;
}

static void gl_init(void)
{
    if (app.gl_ready)
        return;
    load_program();
    if (!app.program)
        die("no usable shader");
    static const float quad[] = { -1, -1, 1, -1, -1, 1, 1, 1 };
    glGenBuffers(1, &app.quad);
    glBindBuffer(GL_ARRAY_BUFFER, app.quad);
    glBufferData(GL_ARRAY_BUFFER, sizeof quad, quad, GL_STATIC_DRAW);
    app.tex_bird = load_texture("bird.pgm", &app.bird_aspect);
    app.tex_text = load_texture("text.pgm", NULL);
    app.tex_digits = load_texture("digits.pgm", NULL);
    app.gl_ready = true;
}

/* ─── Sun ───────────────────────────────────────────────── */

// Today's sunrise and sunset in local hours (NOAA's approximation, good to a
// couple of minutes), for the position in ~/.config/system1/location
// ("lat lon", decimal degrees). Defaults to Aachen.
static void sun_times(float *rise, float *set)
{
    static int cached_yday = -1;
    static float c_rise = 7.0f, c_set = 18.0f;
    time_t wall = time(NULL);
    struct tm tm;
    localtime_r(&wall, &tm);
    if (tm.tm_yday != cached_yday) {
        cached_yday = tm.tm_yday;
        double lat = 50.776, lon = 6.084;
        char path[600];
        snprintf(path, sizeof path, "%s/../location", app.asset_dir);
        FILE *f = fopen(path, "r");
        if (f) {
            if (fscanf(f, "%lf %lf", &lat, &lon) != 2) {
                lat = 50.776;
                lon = 6.084;
            }
            fclose(f);
        }
        double g = 2 * M_PI / 365.0 * tm.tm_yday;
        double eqt = 229.18 * (0.000075 + 0.001868 * cos(g) - 0.032077 * sin(g) - 0.014615 * cos(2 * g) - 0.040849 * sin(2 * g));
        double decl = 0.006918 - 0.399912 * cos(g) + 0.070257 * sin(g) - 0.006758 * cos(2 * g) + 0.000907 * sin(2 * g)
                    - 0.002697 * cos(3 * g) + 0.00148 * sin(3 * g);
        double la = lat * M_PI / 180.0;
        double cosha = cos(90.833 * M_PI / 180.0) / (cos(la) * cos(decl)) - tan(la) * tan(decl);
        double ha = acos(fmax(-1.0, fmin(1.0, cosha))) * 180.0 / M_PI;
        double tz = tm.tm_gmtoff / 3600.0;
        c_rise = (float)((720 - 4 * (lon + ha) - eqt) / 60.0 + tz);
        c_set = (float)((720 - 4 * (lon - ha) - eqt) / 60.0 + tz);
    }
    *rise = c_rise;
    *set = c_set;
}

static void set_uniforms(int w, int h, float seed, float t, float hour)
{
    GLuint p = app.program;
    time_t wall = time(NULL);
    struct tm tm;
    localtime_r(&wall, &tm);
    float rise, set;
    sun_times(&rise, &set);
    glUniform2f(glGetUniformLocation(p, "uSun"), rise, set);
    glUniform2f(glGetUniformLocation(p, "uRes"), w, h);
    glUniform1f(glGetUniformLocation(p, "uTime"), t);
    glUniform1f(glGetUniformLocation(p, "uHour"), hour);
    glUniform3f(glGetUniformLocation(p, "uClock"), tm.tm_hour, tm.tm_min, tm.tm_sec);
    glUniform1f(glGetUniformLocation(p, "uDark"), app.dark);
    glUniform1f(glGetUniformLocation(p, "uSeed"), seed);
    glUniform1f(glGetUniformLocation(p, "uBirdAspect"), app.bird_aspect);
    GLuint tex[] = { app.tex_bird, app.tex_text, app.tex_digits };
    const char *names[] = { "uBird", "uText", "uDigits" };
    for (int i = 0; i < 3; i++) {
        glActiveTexture(GL_TEXTURE0 + i);
        glBindTexture(GL_TEXTURE_2D, tex[i]);
        glUniform1i(glGetUniformLocation(p, names[i]), i);
    }
}

static float local_hour(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    struct tm tm;
    localtime_r(&ts.tv_sec, &tm);
    return tm.tm_hour + tm.tm_min / 60.0f + (tm.tm_sec + ts.tv_nsec / 1e9f) / 3600.0f;
}

static void draw_quad(int w, int h, float seed, float t, float hour)
{
    glViewport(0, 0, w, h);
    glUseProgram(app.program);
    set_uniforms(w, h, seed, t, hour);
    glBindBuffer(GL_ARRAY_BUFFER, app.quad);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, 0);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
}

/* ─── EGL ───────────────────────────────────────────────── */

static void egl_init(void)
{
    app.egl_display = eglGetDisplay((EGLNativeDisplayType)app.display);
    if (app.egl_display == EGL_NO_DISPLAY || !eglInitialize(app.egl_display, NULL, NULL))
        die("cannot initialise EGL");
    eglBindAPI(EGL_OPENGL_ES_API);
    const EGLint cfg_attr[] = {
        EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8,
        EGL_NONE,
    };
    EGLint n;
    if (!eglChooseConfig(app.egl_display, cfg_attr, &app.egl_config, 1, &n) || n < 1)
        die("no EGL config");
    const EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    app.egl_context = eglCreateContext(app.egl_display, app.egl_config, EGL_NO_CONTEXT, ctx_attr);
    if (app.egl_context == EGL_NO_CONTEXT)
        die("cannot create EGL context");
}

/* ─── Outputs ───────────────────────────────────────────── */

static void frame_done(void *data, struct wl_callback *cb, uint32_t time_ms)
{
    struct output *o = data;
    o->frame_ready = true;
    wl_callback_destroy(cb);
}

static const struct wl_callback_listener frame_listener = { .done = frame_done };

static void draw_output(struct output *o, double t)
{
    if (!eglMakeCurrent(app.egl_display, o->egl_surface, o->egl_surface, app.egl_context))
        return;
    gl_init();
    eglSwapInterval(app.egl_display, 0);
    draw_quad(o->width, o->height, o->seed, (float)(t - app.start), local_hour());
    struct wl_callback *cb = wl_surface_frame(o->surface);
    wl_callback_add_listener(cb, &frame_listener, o);
    o->frame_ready = false;
    eglSwapBuffers(app.egl_display, o->egl_surface);
}

static void layer_configure(void *data, struct zwlr_layer_surface_v1 *layer, uint32_t serial, uint32_t w, uint32_t h)
{
    struct output *o = data;
    zwlr_layer_surface_v1_ack_configure(layer, serial);
    if (o->configured && (int)w == o->width && (int)h == o->height)
        return;
    o->width = w;
    o->height = h;
    if (o->egl_window) {
        wl_egl_window_resize(o->egl_window, w, h, 0, 0);
    } else {
        o->egl_window = wl_egl_window_create(o->surface, w, h);
        o->egl_surface = eglCreateWindowSurface(app.egl_display, app.egl_config, (EGLNativeWindowType)o->egl_window, NULL);
    }
    o->configured = true;
    o->frame_ready = true;
}

static void output_destroy(struct output *o);

static void layer_closed(void *data, struct zwlr_layer_surface_v1 *layer)
{
    output_destroy(data);
}

static const struct zwlr_layer_surface_v1_listener layer_listener = {
    .configure = layer_configure,
    .closed = layer_closed,
};

static void output_create_surface(struct output *o)
{
    if (!app.compositor || !app.layer_shell || o->surface)
        return;
    o->surface = wl_compositor_create_surface(app.compositor);
    bool saver = app.mode == MODE_SAVER;
    o->layer = zwlr_layer_shell_v1_get_layer_surface(app.layer_shell, o->surface, o->wl_output,
        saver ? ZWLR_LAYER_SHELL_V1_LAYER_OVERLAY : ZWLR_LAYER_SHELL_V1_LAYER_BOTTOM,
        saver ? "system1-saver" : "system1-bg");
    zwlr_layer_surface_v1_set_anchor(o->layer,
        ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP | ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM |
        ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT | ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT);
    zwlr_layer_surface_v1_set_exclusive_zone(o->layer, -1);
    zwlr_layer_surface_v1_set_keyboard_interactivity(o->layer,
        saver ? ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_EXCLUSIVE : ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE);
    if (!saver) {
        // clicks pass through to whatever is underneath
        struct wl_region *empty = wl_compositor_create_region(app.compositor);
        wl_surface_set_input_region(o->surface, empty);
        wl_region_destroy(empty);
    }
    zwlr_layer_surface_v1_add_listener(o->layer, &layer_listener, o);
    wl_surface_commit(o->surface);
}

static void output_destroy(struct output *o)
{
    if (o->egl_surface)
        eglDestroySurface(app.egl_display, o->egl_surface);
    if (o->egl_window)
        wl_egl_window_destroy(o->egl_window);
    if (o->layer)
        zwlr_layer_surface_v1_destroy(o->layer);
    if (o->surface)
        wl_surface_destroy(o->surface);
    wl_output_release(o->wl_output);
    wl_list_remove(&o->link);
    free(o);
}

/* ─── Input (screensaver only) ──────────────────────────── */

// Ignore the motion/enter events that arrive as the overlay maps
static bool input_armed(void) { return now() - app.start > 1.5; }

static void kb_keymap(void *d, struct wl_keyboard *k, uint32_t f, int32_t fd, uint32_t s) { close(fd); }
static void kb_enter(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf, struct wl_array *keys) {}
static void kb_leave(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf) {}
static void kb_key(void *d, struct wl_keyboard *k, uint32_t s, uint32_t t, uint32_t key, uint32_t state)
{
    if (input_armed())
        quit_flag = 1;
}
static void kb_mods(void *d, struct wl_keyboard *k, uint32_t s, uint32_t a, uint32_t b, uint32_t c, uint32_t g) {}
static void kb_repeat(void *d, struct wl_keyboard *k, int32_t r, int32_t dl) {}
static const struct wl_keyboard_listener kb_listener = {
    kb_keymap, kb_enter, kb_leave, kb_key, kb_mods, kb_repeat,
};

static void ptr_enter(void *d, struct wl_pointer *p, uint32_t s, struct wl_surface *sf, wl_fixed_t x, wl_fixed_t y)
{
    wl_pointer_set_cursor(p, s, NULL, 0, 0); // hide the cursor over the saver
}
static void ptr_leave(void *d, struct wl_pointer *p, uint32_t s, struct wl_surface *sf) {}
static void ptr_motion(void *d, struct wl_pointer *p, uint32_t t, wl_fixed_t x, wl_fixed_t y)
{
    if (input_armed())
        quit_flag = 1;
}
static void ptr_button(void *d, struct wl_pointer *p, uint32_t s, uint32_t t, uint32_t b, uint32_t st)
{
    if (input_armed())
        quit_flag = 1;
}
static void ptr_axis(void *d, struct wl_pointer *p, uint32_t t, uint32_t a, wl_fixed_t v)
{
    if (input_armed())
        quit_flag = 1;
}
static const struct wl_pointer_listener ptr_listener = {
    .enter = ptr_enter, .leave = ptr_leave, .motion = ptr_motion, .button = ptr_button, .axis = ptr_axis,
};

static void seat_caps(void *d, struct wl_seat *seat, uint32_t caps)
{
    if ((caps & WL_SEAT_CAPABILITY_KEYBOARD) && !app.keyboard) {
        app.keyboard = wl_seat_get_keyboard(seat);
        wl_keyboard_add_listener(app.keyboard, &kb_listener, NULL);
    }
    if ((caps & WL_SEAT_CAPABILITY_POINTER) && !app.pointer) {
        app.pointer = wl_seat_get_pointer(seat);
        wl_pointer_add_listener(app.pointer, &ptr_listener, NULL);
    }
}
static void seat_name(void *d, struct wl_seat *s, const char *n) {}
static const struct wl_seat_listener seat_listener = { seat_caps, seat_name };

/* ─── Registry ──────────────────────────────────────────── */

static void registry_global(void *data, struct wl_registry *reg, uint32_t name, const char *iface, uint32_t version)
{
    if (strcmp(iface, wl_compositor_interface.name) == 0) {
        app.compositor = wl_registry_bind(reg, name, &wl_compositor_interface, 4);
    } else if (strcmp(iface, zwlr_layer_shell_v1_interface.name) == 0) {
        app.layer_shell = wl_registry_bind(reg, name, &zwlr_layer_shell_v1_interface, version < 4 ? version : 4);
    } else if (strcmp(iface, wl_seat_interface.name) == 0 && app.mode == MODE_SAVER && !app.seat) {
        app.seat = wl_registry_bind(reg, name, &wl_seat_interface, 4); // v5+ adds pointer events these listeners lack
        wl_seat_add_listener(app.seat, &seat_listener, NULL);
    } else if (strcmp(iface, wl_output_interface.name) == 0) {
        struct output *o = calloc(1, sizeof *o);
        o->name = name;
        o->wl_output = wl_registry_bind(reg, name, &wl_output_interface, version < 3 ? version : 3);
        o->seed = (float)(name * 7.31 - floor(name * 7.31 / 100.0) * 100.0);
        wl_list_insert(&app.outputs, &o->link);
        output_create_surface(o); // no-op until the shell is bound; hotplugged outputs get one here
    }
}

static void registry_remove(void *data, struct wl_registry *reg, uint32_t name)
{
    struct output *o, *tmp;
    wl_list_for_each_safe(o, tmp, &app.outputs, link) {
        if (o->name == name)
            output_destroy(o);
    }
}

static const struct wl_registry_listener registry_listener = { registry_global, registry_remove };

/* ─── Snapshot ──────────────────────────────────────────── */

static int snapshot(int w, int h, bool dark, float hour, const char *out)
{
    if (!eglMakeCurrent(app.egl_display, EGL_NO_SURFACE, EGL_NO_SURFACE, app.egl_context))
        die("surfaceless context unsupported");
    gl_init();
    GLuint fbo, rb;
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glGenRenderbuffers(1, &rb);
    glBindRenderbuffer(GL_RENDERBUFFER, rb);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_RGB565, w, h);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_RENDERBUFFER, rb);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
        die("incomplete framebuffer");
    app.dark = dark ? 1.0f : 0.0f;
    // a moment where the bird is on screen and a caption is showing
    draw_quad(w, h, 3.0f, 95.0f, hour);
    unsigned char *px = malloc((size_t)w * h * 4);
    glReadPixels(0, 0, w, h, GL_RGBA, GL_UNSIGNED_BYTE, px);
    FILE *f = fopen(out, "wb");
    if (!f)
        die("cannot write snapshot");
    fprintf(f, "P6\n%d %d\n255\n", w, h);
    for (int y = h - 1; y >= 0; y--)
        for (int x = 0; x < w; x++)
            fwrite(px + ((size_t)y * w + x) * 4, 1, 3, f);
    fclose(f);
    free(px);
    return 0;
}

/* ─── Main ──────────────────────────────────────────────── */

static void on_signal(int sig)
{
    if (sig == SIGUSR1)
        pause_flag = !pause_flag;
    else if (sig == SIGHUP)
        reload_flag = 1;
    else
        quit_flag = 1;
}

int main(int argc, char **argv)
{
    const char *home = getenv("HOME");
    const char *cfg = getenv("XDG_CONFIG_HOME");
    const char *cache = getenv("XDG_CACHE_HOME");
    char base[400];
    if (cfg)
        snprintf(base, sizeof base, "%s/system1", cfg);
    else
        snprintf(base, sizeof base, "%s/.config/system1", home);
    snprintf(app.shader_dir, sizeof app.shader_dir, "%s/shaders", base);
    snprintf(app.asset_dir, sizeof app.asset_dir, "%s/assets", base);
    if (cache)
        snprintf(app.mode_file, sizeof app.mode_file, "%s/system1/mode", cache);
    else
        snprintf(app.mode_file, sizeof app.mode_file, "%s/.cache/system1/mode", home);

    app.mode = MODE_BG;
    // the scene moves slowly; a low rate keeps the GPU in its idle clocks
    const char *fps = getenv("SYSTEM1_FPS");
    app.fps = fps && atof(fps) > 0 ? atof(fps) : 15;
    if (argc > 1 && strcmp(argv[1], "--saver") == 0)
        app.mode = MODE_SAVER;
    else if (argc > 1 && strcmp(argv[1], "--snapshot") == 0)
        app.mode = MODE_SNAPSHOT;
    else if (argc > 1) {
        fprintf(stderr, "usage: %s [--saver | --snapshot W H dark|light HOUR out.ppm]\n", argv[0]);
        return 2;
    }
    const char *scene = getenv("SYSTEM1_SCENE");
    app.saver_scene = app.mode == MODE_SAVER || (scene && strcmp(scene, "saver") == 0);
    if (app.mode == MODE_SNAPSHOT && argc != 7) {
        fprintf(stderr, "usage: %s --snapshot W H dark|light HOUR out.ppm\n", argv[0]);
        return 2;
    }

    app.display = wl_display_connect(NULL);
    if (!app.display)
        die("cannot connect to the Wayland display");
    wl_list_init(&app.outputs);
    egl_init();
    app.start = now();

    if (app.mode == MODE_SNAPSHOT)
        return snapshot(atoi(argv[2]), atoi(argv[3]), strcmp(argv[4], "light") != 0, atof(argv[5]), argv[6]);

    struct sigaction sa = { .sa_handler = on_signal };
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGUSR1, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);

    struct wl_registry *reg = wl_display_get_registry(app.display);
    wl_registry_add_listener(reg, &registry_listener, NULL);
    wl_display_roundtrip(app.display);
    if (!app.compositor || !app.layer_shell)
        die("compositor lacks wlr-layer-shell");
    struct output *o;
    wl_list_for_each(o, &app.outputs, link)
        output_create_surface(o);
    wl_display_roundtrip(app.display);

    app.dark = app.dark_target = app.mode == MODE_SAVER ? 1.0f : read_mode_file();
    double last = now();
    int fd = wl_display_get_fd(app.display);

    while (!quit_flag) {
        while (wl_display_prepare_read(app.display) != 0)
            wl_display_dispatch_pending(app.display);
        wl_display_flush(app.display);

        // sleep until the next output is due, or 1 s while paused / waiting on frame callbacks
        double t = now(), wake = t + 1.0;
        if (!pause_flag) {
            wl_list_for_each(o, &app.outputs, link) {
                if (o->configured && o->frame_ready && o->next_due < wake)
                    wake = o->next_due;
            }
        }
        int timeout = wake <= t ? 0 : (int)((wake - t) * 1000) + 1;
        struct pollfd pfd = { fd, POLLIN, 0 };
        int r = poll(&pfd, 1, timeout);
        if (r > 0 && (pfd.revents & POLLIN))
            wl_display_read_events(app.display);
        else
            wl_display_cancel_read(app.display);
        if (r < 0 && errno != EINTR)
            break;
        if (wl_display_dispatch_pending(app.display) < 0)
            break;

        if (reload_flag && app.gl_ready) {
            reload_flag = 0;
            o = wl_container_of(app.outputs.next, o, link);
            if (!wl_list_empty(&app.outputs) && o->egl_surface &&
                eglMakeCurrent(app.egl_display, o->egl_surface, o->egl_surface, app.egl_context))
                load_program();
        }

        t = now();
        if (app.mode == MODE_BG)
            poll_mode_file();
        // ~1.5 s dither dissolve between light and dark
        float step = (float)(t - last) / 1.5f;
        last = t;
        if (app.dark < app.dark_target)
            app.dark = fminf(app.dark + step, app.dark_target);
        else if (app.dark > app.dark_target)
            app.dark = fmaxf(app.dark - step, app.dark_target);

        if (pause_flag)
            continue;
        wl_list_for_each(o, &app.outputs, link) {
            if (o->configured && o->frame_ready && t >= o->next_due) {
                draw_output(o, t);
                o->next_due = fmax(o->next_due + 1.0 / app.fps, t);
            }
        }
    }

    struct output *tmp;
    wl_list_for_each_safe(o, tmp, &app.outputs, link)
        output_destroy(o);
    wl_display_flush(app.display);
    wl_display_disconnect(app.display);
    return 0;
}
