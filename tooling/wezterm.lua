-- WezTerm config — tuned for Ashley's 2015 MacBook Pro (8GB, Intel iGPU)
-- Polished dark theme, opens in ~/Code, low-overhead rendering.

local wezterm = require 'wezterm'
local config = wezterm.config_builder and wezterm.config_builder() or {}
local act = wezterm.action

-- ── Always start in the Code folder ─────────────────────────────────────────
config.default_cwd = wezterm.home_dir .. '/Code'

-- ── Dark theme (refined) ────────────────────────────────────────────────────
config.color_scheme = 'Catppuccin Mocha'
-- Tweak a few colours for a cleaner, deeper look
config.colors = {
  background = '#11111b',          -- deep near-black (less eye strain than pure black)
  foreground = '#cdd6f4',
  cursor_bg  = '#89b4fa',          -- soft blue cursor
  cursor_border = '#89b4fa',
  cursor_fg  = '#11111b',
  selection_bg = '#313244',
  selection_fg = '#cdd6f4',
  tab_bar = {
    background = '#0b0b12',
    active_tab   = { bg_color = '#1e1e2e', fg_color = '#89b4fa', intensity = 'Bold' },
    inactive_tab = { bg_color = '#0b0b12', fg_color = '#6c7086' },
    inactive_tab_hover = { bg_color = '#181825', fg_color = '#cdd6f4' },
    new_tab      = { bg_color = '#0b0b12', fg_color = '#6c7086' },
    new_tab_hover= { bg_color = '#181825', fg_color = '#cdd6f4' },
  },
}
config.window_background_opacity = 1.0          -- no transparency (saves GPU)
config.macos_window_background_blur = 0

-- ── Font — crisp coding font with good fallbacks ────────────────────────────
config.font = wezterm.font_with_fallback {
  { family = 'JetBrains Mono', weight = 'Medium' },
  'Menlo',
  'Monaco',
}
config.font_size = 14.0
config.line_height = 1.05
config.freetype_load_target = 'Light'           -- crisper text on non-retina

-- ── Window & tab bar look ───────────────────────────────────────────────────
config.window_padding = { left = 12, right = 12, top = 10, bottom = 8 }
config.window_decorations = 'RESIZE'             -- clean, no heavy title bar
config.use_fancy_tab_bar = true
config.tab_bar_at_bottom = false
config.hide_tab_bar_if_only_one_tab = true
config.show_new_tab_button_in_tab_bar = true
config.window_frame = {
  font = wezterm.font { family = 'JetBrains Mono', weight = 'Bold' },
  font_size = 12.0,
  active_titlebar_bg = '#0b0b12',
  inactive_titlebar_bg = '#0b0b12',
}
config.inactive_pane_hsb = { saturation = 0.9, brightness = 0.7 }  -- dim unfocused splits

-- ── Performance for an old Intel GPU ────────────────────────────────────────
config.front_end = 'OpenGL'
config.max_fps = 30
config.animation_fps = 1
config.cursor_blink_rate = 0
config.scrollback_lines = 10000                  -- BOUNDED (saves RAM vs iTerm)
config.enable_scroll_bar = false
config.audible_bell = 'Disabled'

-- ── Keys ────────────────────────────────────────────────────────────────────
config.keys = {
  { key = 'd', mods = 'CMD',       action = act.SplitHorizontal { domain = 'CurrentPaneDomain' } },
  { key = 'd', mods = 'CMD|SHIFT', action = act.SplitVertical   { domain = 'CurrentPaneDomain' } },
  { key = 'LeftArrow',  mods = 'CMD', action = act.ActivatePaneDirection 'Left' },
  { key = 'RightArrow', mods = 'CMD', action = act.ActivatePaneDirection 'Right' },
  { key = 'UpArrow',    mods = 'CMD', action = act.ActivatePaneDirection 'Up' },
  { key = 'DownArrow',  mods = 'CMD', action = act.ActivatePaneDirection 'Down' },
  { key = 'g', mods = 'CMD', action = act.SpawnCommandInNewTab {
      args = { '/bin/zsh', '-lc', 'gmux attach || gmux status; exec zsh' },
      cwd  = wezterm.home_dir .. '/Code' } },
  { key = 'r', mods = 'CMD', action = act.SpawnCommandInNewTab {
      args = { '/bin/zsh', '-lc', 'cd ~/Code && qalcode; exec zsh' },
      cwd  = wezterm.home_dir .. '/Code' } },
}

return config
