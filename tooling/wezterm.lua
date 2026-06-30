-- WezTerm config — tuned for Ashley's 2015 MacBook Pro (8GB, Intel iGPU)
-- Dark theme, opens in ~/Code, low-overhead rendering.

local wezterm = require 'wezterm'
local config = wezterm.config_builder and wezterm.config_builder() or {}

-- ── Start in the Code folder ────────────────────────────────────────────────
config.default_cwd = wezterm.home_dir .. '/Code'

-- ── Dark theme ──────────────────────────────────────────────────────────────
config.color_scheme = 'Catppuccin Mocha'
config.window_background_opacity = 1.0          -- no transparency (saves GPU)
config.macos_window_background_blur = 0

-- ── Performance for an old Intel GPU ────────────────────────────────────────
-- WebGpu/OpenGL can strain the HD6100 iGPU; software is steadier and won't leak.
config.front_end = 'OpenGL'                      -- try OpenGL first; switch to 'Software' if it stutters
config.max_fps = 30                              -- cap redraw (huge win for TUIs like qalcode)
config.animation_fps = 1                         -- minimal cursor/scroll animation
config.cursor_blink_rate = 0                     -- no blinking = fewer redraws
config.scrollback_lines = 10000                  -- BOUNDED (this is what saves RAM vs iTerm)
config.enable_scroll_bar = false

-- ── Fonts / look ────────────────────────────────────────────────────────────
config.font_size = 14.0
config.window_padding = { left = 8, right = 8, top = 6, bottom = 6 }
config.window_decorations = 'TITLE | RESIZE'
config.hide_tab_bar_if_only_one_tab = true
config.audible_bell = 'Disabled'

-- ── Sensible keys ───────────────────────────────────────────────────────────
config.keys = {
  -- Splits (like panes): Cmd+D side-by-side, Cmd+Shift+D stacked
  { key = 'd', mods = 'CMD',       action = wezterm.action.SplitHorizontal { domain = 'CurrentPaneDomain' } },
  { key = 'd', mods = 'CMD|SHIFT', action = wezterm.action.SplitVertical   { domain = 'CurrentPaneDomain' } },
  -- Move between splits with Cmd+arrow
  { key = 'LeftArrow',  mods = 'CMD', action = wezterm.action.ActivatePaneDirection 'Left' },
  { key = 'RightArrow', mods = 'CMD', action = wezterm.action.ActivatePaneDirection 'Right' },
  { key = 'UpArrow',    mods = 'CMD', action = wezterm.action.ActivatePaneDirection 'Up' },
  { key = 'DownArrow',  mods = 'CMD', action = wezterm.action.ActivatePaneDirection 'Down' },
  -- Cmd+G: open a fresh tab and launch the gmux multiplexer view
  { key = 'g', mods = 'CMD', action = wezterm.action.SpawnCommandInNewTab {
      args = { '/bin/zsh', '-lc', 'gmux attach || gmux status; exec zsh' },
      cwd  = wezterm.home_dir .. '/Code',
  }},
  -- Cmd+R: open a fresh tab running qalcode in the Code folder
  { key = 'r', mods = 'CMD', action = wezterm.action.SpawnCommandInNewTab {
      args = { '/bin/zsh', '-lc', 'cd ~/Code && qalcode; exec zsh' },
      cwd  = wezterm.home_dir .. '/Code',
  }},
}

-- New tabs/windows open in the Code folder too
config.default_cwd = wezterm.home_dir .. '/Code'

return config
