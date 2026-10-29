-- System 1: 1-bit black and white with one red, after the 1984 Macintosh.
-- Light/dark follows ~/.cache/system1/mode, which Noctalia's hook keeps in
-- sync with sunrise/sunset. Red only ever flashes; nothing stays red.

local HOME = os.getenv("HOME")
local S1 = HOME .. "/.config/system1"
local RED = "rgba(e00000ff)"
local CLEAR = "rgba(00000000)"

local PALETTE = {
    dark  = { fg = "rgba(ffffffff)", dim = "rgba(4a4a4aff)", bg = "rgba(000000ff)" },
    light = { fg = "rgba(000000ff)", dim = "rgba(9a9a9aff)", bg = "rgba(ffffffff)" },
}

local function read_mode()
    local f = io.open(HOME .. "/.cache/system1/mode", "r")
    local m = f and f:read("l")
    if f then f:close() end
    return PALETTE[m] and m or "dark"
end

local mode = read_mode()

hl.config({
    general = {
        gaps_in = 6,
        gaps_out = 14,
        border_size = 2,
        extend_border_grab_area = 10,
        resize_on_border = true,
    },
    decoration = {
        rounding = 0,
        dim_special = 0.5,
        active_opacity = 1.0,
        inactive_opacity = 0.9,
        fullscreen_opacity = 1,
        blur = { enabled = false },
        -- the hard offset drop shadow of a System 1 window, on the focused one only.
        -- Hyprland also paints it under the window, so it takes the paper colour:
        -- see-through windows then read slightly more solid instead of turning grey
        shadow = {
            enabled = true,
            sharp = true,
            range = 0,
            render_power = 1,
            offset = { 5, 5 },
            color_inactive = CLEAR,
        },
    },
    group = {
        groupbar = {
            font_family = "Departure Mono",
            gradients = false,
        },
    },
})

local function apply(m)
    local p = PALETTE[m]
    hl.config({
        general = { col = { active_border = p.fg, inactive_border = p.dim } },
        decoration = { shadow = { color = p.bg } },
        group = {
            col = {
                border_active = p.fg,
                border_inactive = p.dim,
                border_locked_active = p.fg,
                border_locked_inactive = p.dim,
            },
            groupbar = {
                col = { active = p.fg, inactive = p.dim, locked_active = p.fg, locked_inactive = p.dim },
                text_color = p.bg,
                text_color_inactive = p.fg,
            },
        },
        misc = { background_color = p.bg, col = { splash = p.fg } },
    })
end

apply(mode)

-- Called by system1-mode: hyprctl dispatch System1ApplyMode
function System1ApplyMode()
    mode = read_mode()
    apply(mode)
end

-- Focus changes flash the new window's border red for a moment
local flash
hl.on("window.active", function()
    hl.config({ general = { col = { active_border = RED } } })
    flash = hl.timer(function()
        hl.config({ general = { col = { active_border = PALETTE[mode].fg } } })
    end, { timeout = 200, type = "oneshot" })
end)
hl.on("window.urgent", function()
    hl.notification.create({ text = "注意 — a window wants attention", timeout = 2500, color = RED })
end)

-- Pixelated icon font for Noctalia (built by src/pixel-icons.py)
NOCTALIA_ASSETS = S1 .. "/noctalia/assets"

-- Kanji workspace numbers for the bar (applied by config/theme.lua)
WORKSPACE_NAMES = { "一", "二", "三", "四", "五", "六", "七", "八", "九", "十" }

hl.on("hyprland.start", function()
    hl.exec_cmd(S1 .. "/bin/system1-bg")
end)

hl.layer_rule({ match = { namespace = "^system1-bg$" }, no_anim = true })
hl.layer_rule({ match = { namespace = "^system1-saver$" }, animation = "fade" })

hl.bind("SUPER + CONTROL + B", hl.dsp.exec_cmd("pkill -USR1 -fx ~/.config/system1/bin/system1-bg"))       -- pause/resume the background
hl.bind("SUPER + CONTROL + M", hl.dsp.exec_cmd("noctalia msg theme-mode-toggle"))  -- light/dark by hand
hl.bind("SUPER + CONTROL + S", hl.dsp.exec_cmd(S1 .. "/bin/system1-bg --saver"))   -- screensaver now
