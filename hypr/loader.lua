-- Theme loader for System 1. Require it from hyprland.lua *after* your own
-- look settings:  require("themes.loader")
--
-- ~/.config/hypr/theme-name holds the active theme. "system1" loads
-- themes/system1/init.lua; any other name loads themes/<name>/init.lua if it
-- exists, and "default" (or a missing file) loads nothing, leaving your own
-- config as it is. ~/.config/system1/bin/theme-switch changes it and reloads.

local HOME = os.getenv("HOME")
local SWITCH = HOME .. "/.config/system1/bin/theme-switch"

THEME = "default"
local f = io.open(HOME .. "/.config/hypr/theme-name", "r")
if f then
    THEME = f:read("l") or THEME
    f:close()
end

-- a theme may set these; reset them so switching away clears them
WORKSPACE_NAMES = nil
NOCTALIA_ASSETS = nil

local function exists(path)
    local h = io.open(path, "r")
    if h then h:close() end
    return h ~= nil
end

if THEME ~= "default" and exists(HOME .. "/.config/hypr/themes/" .. THEME .. "/init.lua") then
    local ok, err = pcall(require, "themes." .. THEME .. ".init")
    if not ok then
        hl.notification.create({ text = "Theme '" .. THEME .. "' failed to load: " .. tostring(err), timeout = 10000 })
        THEME = "default"
        WORKSPACE_NAMES = nil
        NOCTALIA_ASSETS = nil
    end
end

-- Switch System 1 on and off from either theme
hl.bind("SUPER + CONTROL + T", hl.dsp.exec_cmd(SWITCH .. " toggle"))

-- Workspace names: a theme may set WORKSPACE_NAMES = { "一", "二", ... }; any
-- other theme gets plain numbers back. Only workspaces 1..10 are touched.
local function name_workspaces()
    for _, ws in ipairs(hl.get_workspaces()) do
        local id = ws.id
        if id and id >= 1 and id <= 10 and not ws.special then
            local want = (WORKSPACE_NAMES and WORKSPACE_NAMES[id]) or tostring(id)
            if ws.name ~= want then
                hl.dispatch(hl.dsp.workspace.rename({ workspace = id, name = want }))
            end
        end
    end
end
name_workspaces()
hl.on("workspace.created", name_workspaces)

-- Noctalia reads its icon font from here at startup (theme-switch restarts it)
hl.env("NOCTALIA_ASSETS_DIR", NOCTALIA_ASSETS or "/usr/share/noctalia/assets")
