#!/usr/bin/env python3
"""
Moida Mansion - Port for R36S / Retro Handhelds & PC
Authentic retro LCD game runner powered by Lucas Pope's original engine.
"""

import os
import sys
import time
import json
import array
import subprocess
import shutil
import glob
import pygame

# ---------------------------------------------------------------------------
# Configuration & Constants
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 640
SCREEN_HEIGHT = 480
FPS = 60

# Mode A: Framed Bezel (Inside red plastic casing with white borders cropped out)
BEZEL_CROP_RECT = pygame.Rect(21, 13, 594, 503)
BEZEL_SCALE_W = 566
BEZEL_SCALE_H = 480
BEZEL_POS_X = (SCREEN_WIDTH - BEZEL_SCALE_W) // 2  # 37 (Centered with 37px black pillarbox)
BEZEL_POS_Y = 0

BEZEL_LCD_X = 86
BEZEL_LCD_Y = 98
BEZEL_LCD_W = 464
BEZEL_LCD_H = 334

# Mode B: Fullscreen LCD (Maximum screen real estate)
FULL_LCD_X = 0
FULL_LCD_Y = 10
FULL_LCD_W = 640
FULL_LCD_H = 460

# Authentic Palette (Sampled from Lucas Pope's original game)
LCD_BG_COLOR = (200, 204, 196)         # Warm vintage greyish-green LCD background
LCD_SHADOW_COLOR = (155, 159, 151)     # 3D LCD crystal drop shadow
LCD_ACTIVE_COLOR = (26, 28, 30)        # Crisp active segment black
BACKDROP_COLOR = (0, 0, 0)             # Pure black outside the handheld casing

# Game States
STATE_GAME = 0
STATE_MANUAL = 1
STATE_MENU = 2
STATE_MISSING_ASSETS = 3
STATE_CONTROLS = 4


# ---------------------------------------------------------------------------
# Asset Paths Helper
# ---------------------------------------------------------------------------
def find_asset(patterns, search_dirs=None):
    if isinstance(patterns, str):
        patterns = [patterns]
    if search_dirs is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        search_dirs = [
            base_dir,
            os.path.join(base_dir, 'gamedata'),
            os.path.join(base_dir, 'Moida Mansion_files'),
            os.path.join(base_dir, 'Moida Mansion by dukope_files'),
        ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for pat in patterns:
            matches = glob.glob(os.path.join(d, pat))
            if matches and os.path.isfile(matches[0]):
                return matches[0]
    return None


# ---------------------------------------------------------------------------
# Polygon Path Parser
# ---------------------------------------------------------------------------
def parse_svg_path(p_str, sx, sy, ox=0, oy=0):
    """Parses SVG path tokens (M, L, Z and coordinates) into pygame polygon point lists."""
    polys = []
    curr = []
    tokens = p_str.strip().split()
    i = 0
    while i < len(tokens):
        cmd = tokens[i]
        if cmd in ('M', 'L'):
            x = float(tokens[i+1]) * sx + ox
            y = float(tokens[i+2]) * sy + oy
            curr.append((int(round(x)), int(round(y))))
            i += 3
        elif cmd == 'Z':
            if len(curr) >= 3:
                polys.append(curr)
            curr = []
            i += 1
        elif cmd[0] in '-+0123456789':
            x = float(tokens[i]) * sx + ox
            y = float(tokens[i+1]) * sy + oy
            curr.append((int(round(x)), int(round(y))))
            i += 2
        else:
            i += 1
    if len(curr) >= 3:
        polys.append(curr)
    return polys


# ---------------------------------------------------------------------------
# Audio Synthesizer (Retro Piezo Buzzer)
# ---------------------------------------------------------------------------
class PiezoSynthesizer:
    def __init__(self, sample_rate=44100):
        self.enabled = True
        self.sample_rate = sample_rate
        self.channels = 2
        self.cache = {}
        try:
            pygame.mixer.init(frequency=sample_rate, size=-16, channels=2, buffer=2048)
            init_tuple = pygame.mixer.get_init()
            if init_tuple:
                self.sample_rate = init_tuple[0]
                self.channels = init_tuple[2]
        except Exception as e:
            print(f"[Audio] Mixer init failed: {e}", file=sys.stderr)
            self.enabled = False

    def play_tone(self, freq, duration_ms=80, volume=0.22):
        if not self.enabled or freq <= 20:
            return
        
        key = (round(freq, 1), int(duration_ms))
        sound = self.cache.get(key)
        
        if sound is None:
            try:
                n_samples = int(self.sample_rate * (duration_ms / 1000.0))
                period = self.sample_rate / freq
                amp = int(32767 * volume)
                samples = array.array('h')
                for i in range(n_samples):
                    val = amp if (i % period) < (period / 2) else -amp
                    if self.channels == 2:
                        samples.append(val)
                        samples.append(val)
                    else:
                        samples.append(val)
                sound = pygame.mixer.Sound(samples)
                self.cache[key] = sound
            except Exception as e:
                return

        sound.play()


# ---------------------------------------------------------------------------
# LCD Renderer
# ---------------------------------------------------------------------------
class LCDRenderer:
    def __init__(self, assets_path, bezel_path=None, glass_path=None):
        with open(assets_path, 'r', encoding='utf-8') as f:
            self.asset_data = json.load(f)
            
        self.segments = self.asset_data['segments']
        self.num_segments = len(self.segments)
        
        orig_w, orig_h = 3000.0, 2160.0
        
        # Mode B: Fullscreen (640x460 at 0, 10)
        self.scale_full_x = FULL_LCD_W / orig_w
        self.scale_full_y = FULL_LCD_H / orig_h
        self.polys_full = []
        self.shadow_polys_full = []
        
        # Determine bezel geometry dynamically based on provided asset
        self.bezel_texture = None
        self.bezel_pos = (BEZEL_POS_X, BEZEL_POS_Y)
        self.bezel_lcd_rect = (BEZEL_LCD_X, BEZEL_LCD_Y, BEZEL_LCD_W, BEZEL_LCD_H)

        if bezel_path and os.path.isfile(bezel_path):
            raw_bezel = pygame.image.load(bezel_path)
            if pygame.display.get_surface():
                raw_bezel = raw_bezel.convert_alpha()
            
            raw_w, raw_h = raw_bezel.get_size()
            if raw_w >= 1500:
                # Raw hardware_jpg.jpg from itch.io (1865x2740)
                crop_rect = pygame.Rect(60, 120, 1745, 1420)
                cropped = raw_bezel.subsurface(crop_rect)
                scale = 480.0 / 1420.0
                scale_w = int(1745 * scale)
                scale_h = 480
                pos_x = (SCREEN_WIDTH - scale_w) // 2
                pos_y = 0
                lcd_x = int((195 - 60) * scale) + pos_x
                lcd_y = int((408 - 120) * scale)
                lcd_w = int(1476 * scale)
                lcd_h = int(1062 * scale)
                
                self.bezel_texture = pygame.transform.smoothscale(cropped, (scale_w, scale_h))
                if pygame.display.get_surface() and not (self.bezel_texture.get_flags() & pygame.SRCALPHA):
                    self.bezel_texture = self.bezel_texture.convert_alpha()
                hole = pygame.Surface((lcd_w, lcd_h), pygame.SRCALPHA)
                hole.fill((0, 0, 0, 0))
                self.bezel_texture.blit(hole, (lcd_x - pos_x, lcd_y), special_flags=pygame.BLEND_RGBA_MIN)
                self.bezel_pos = (pos_x, pos_y)
                self.bezel_lcd_rect = (lcd_x, lcd_y, lcd_w, lcd_h)
            else:
                # Pre-cropped / custom bezel.png
                cropped = raw_bezel.subsurface(BEZEL_CROP_RECT)
                self.bezel_texture = pygame.transform.smoothscale(cropped, (BEZEL_SCALE_W, BEZEL_SCALE_H))
                if pygame.display.get_surface() and not (self.bezel_texture.get_flags() & pygame.SRCALPHA):
                    self.bezel_texture = self.bezel_texture.convert_alpha()
                hole_x = BEZEL_LCD_X - BEZEL_POS_X
                hole_y = BEZEL_LCD_Y - BEZEL_POS_Y
                hole = pygame.Surface((BEZEL_LCD_W, BEZEL_LCD_H), pygame.SRCALPHA)
                hole.fill((0, 0, 0, 0))
                self.bezel_texture.blit(hole, (hole_x, hole_y), special_flags=pygame.BLEND_RGBA_MIN)
                self.bezel_pos = (BEZEL_POS_X, BEZEL_POS_Y)
                self.bezel_lcd_rect = (BEZEL_LCD_X, BEZEL_LCD_Y, BEZEL_LCD_W, BEZEL_LCD_H)

        b_x, b_y, b_w, b_h = self.bezel_lcd_rect
        self.scale_bezel_x = b_w / orig_w
        self.scale_bezel_y = b_h / orig_h
        self.polys_bezel = []
        self.shadow_polys_bezel = []
        
        for seg in self.segments:
            seg_polys_full = []
            seg_sh_full = []
            seg_polys_bezel = []
            seg_sh_bezel = []
            
            for p_str in seg['paths']:
                p_full = parse_svg_path(p_str, self.scale_full_x, self.scale_full_y, FULL_LCD_X, FULL_LCD_Y)
                p_bezel = parse_svg_path(p_str, self.scale_bezel_x, self.scale_bezel_y, b_x, b_y)
                seg_polys_full.extend(p_full)
                seg_polys_bezel.extend(p_bezel)
                
                sh_full = parse_svg_path(p_str, self.scale_full_x, self.scale_full_y, FULL_LCD_X + 2, FULL_LCD_Y + 2)
                sh_bezel = parse_svg_path(p_str, self.scale_bezel_x, self.scale_bezel_y, b_x + 1, b_y + 2)
                seg_sh_full.extend(sh_full)
                seg_sh_bezel.extend(sh_bezel)

            self.polys_full.append(seg_polys_full)
            self.shadow_polys_full.append(seg_sh_full)
            self.polys_bezel.append(seg_polys_bezel)
            self.shadow_polys_bezel.append(seg_sh_bezel)
            
        # Optional Ghost segment overlay surfaces
        self.ghost_full_faint = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self.ghost_full_vintage = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self.ghost_bezel_faint = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        self.ghost_bezel_vintage = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        
        for seg_polys in self.polys_full:
            for poly in seg_polys:
                pygame.draw.polygon(self.ghost_full_faint, (20, 25, 26, 10), poly)
                pygame.draw.polygon(self.ghost_full_vintage, (20, 25, 26, 20), poly)

        for seg_polys in self.polys_bezel:
            for poly in seg_polys:
                pygame.draw.polygon(self.ghost_bezel_faint, (20, 25, 26, 10), poly)
                pygame.draw.polygon(self.ghost_bezel_vintage, (20, 25, 26, 20), poly)

        # Load Glass Glare Reflection Overlays
        self.glass_full_subtle = None
        self.glass_full_vintage = None
        self.glass_bezel_subtle = None
        self.glass_bezel_vintage = None
        
        if glass_path and os.path.isfile(glass_path):
            raw_glass = pygame.image.load(glass_path)
            
            scaled_full = pygame.transform.smoothscale(raw_glass, (FULL_LCD_W, FULL_LCD_H))
            self.glass_full_subtle = scaled_full.copy()
            self.glass_full_subtle.set_alpha(18)
            self.glass_full_vintage = scaled_full.copy()
            self.glass_full_vintage.set_alpha(38)
            
            scaled_bezel = pygame.transform.smoothscale(raw_glass, (b_w, b_h))
            self.glass_bezel_subtle = scaled_bezel.copy()
            self.glass_bezel_subtle.set_alpha(18)
            self.glass_bezel_vintage = scaled_bezel.copy()
            self.glass_bezel_vintage.set_alpha(38)

    def render(self, screen, active_indices, mode_bezel=True, glass_mode=0, ghost_mode=0):
        screen.fill(BACKDROP_COLOR)

        if mode_bezel and self.bezel_texture:
            b_x, b_y, b_w, b_h = self.bezel_lcd_rect
            lcd_rect = self.bezel_lcd_rect
            polys = self.polys_bezel
            sh_polys = self.shadow_polys_bezel
            ghost_faint = self.ghost_bezel_faint
            ghost_vintage = self.ghost_bezel_vintage
            glass_s = self.glass_bezel_subtle
            glass_v = self.glass_bezel_vintage
            glass_pos = (b_x, b_y)
        else:
            lcd_rect = (FULL_LCD_X, FULL_LCD_Y, FULL_LCD_W, FULL_LCD_H)
            polys = self.polys_full
            sh_polys = self.shadow_polys_full
            ghost_faint = self.ghost_full_faint
            ghost_vintage = self.ghost_full_vintage
            glass_s = self.glass_full_subtle
            glass_v = self.glass_full_vintage
            glass_pos = (FULL_LCD_X, FULL_LCD_Y)

        # 1. Clean LCD Background Surface
        pygame.draw.rect(screen, LCD_BG_COLOR, lcd_rect)

        # 2. Optional Ghost Unlit Segments (Default 0 = Off / Completely Clean!)
        if ghost_mode == 1:
            screen.blit(ghost_faint, (0, 0))
        elif ghost_mode == 2:
            screen.blit(ghost_vintage, (0, 0))

        # 3. Active Segment Drop Shadows (3D Crystal Depth)
        for idx in active_indices:
            if idx < self.num_segments:
                for poly in sh_polys[idx]:
                    pygame.draw.polygon(screen, LCD_SHADOW_COLOR, poly)

        # 4. Active Segment Black Bodies
        for idx in active_indices:
            if idx < self.num_segments:
                for poly in polys[idx]:
                    pygame.draw.polygon(screen, LCD_ACTIVE_COLOR, poly)

        # 5. Apply Glass Glare Reflection (if enabled)
        if glass_mode == 1 and glass_s:
            screen.blit(glass_s, glass_pos, special_flags=pygame.BLEND_ADD)
        elif glass_mode == 2 and glass_v:
            screen.blit(glass_v, glass_pos, special_flags=pygame.BLEND_ADD)

        # 6. Composite Outer Illustrated Red Bezel (Cropped, with transparent screen window)
        if mode_bezel and self.bezel_texture:
            screen.blit(self.bezel_texture, self.bezel_pos)


# ---------------------------------------------------------------------------
# In-Game 12-Page Instruction Manual Viewer
# ---------------------------------------------------------------------------
class ManualViewer:
    def __init__(self, manual_path=None):
        self.pages = []
        self.current_page = 0
        self.font_header = None
        self.font_footer = None
        self.is_loaded = False
        
        pygame.font.init()
        self.font_header = pygame.font.SysFont('Arial', 18, bold=True)
        self.font_footer = pygame.font.SysFont('Arial', 15)
        
        if manual_path and os.path.isfile(manual_path):
            try:
                sheet = pygame.image.load(manual_path)
                for row in range(6):
                    for col in range(2):
                        rect = pygame.Rect(col * 1000, row * 600, 1000, 600)
                        sub = sheet.subsurface(rect)
                        scaled = pygame.transform.smoothscale(sub, (640, 384))
                        self.pages.append(scaled)
                self.is_loaded = True
            except Exception as e:
                print(f"[Manual] Slicing failed: {e}", file=sys.stderr)

    def next_page(self):
        if self.is_loaded and len(self.pages) > 0:
            self.current_page = (self.current_page + 1) % len(self.pages)

    def prev_page(self):
        if self.is_loaded and len(self.pages) > 0:
            self.current_page = (self.current_page - 1 + len(self.pages)) % len(self.pages)

    def render(self, screen):
        screen.fill(BACKDROP_COLOR)
        
        if self.is_loaded and len(self.pages) > 0:
            screen.blit(self.pages[self.current_page], (0, 48))
            
            header_str = f"INSTRUCTION MANUAL  —  PAGE {self.current_page + 1} / {len(self.pages)}"
            h_surf = self.font_header.render(header_str, True, (240, 240, 240))
            screen.blit(h_surf, (SCREEN_WIDTH // 2 - h_surf.get_width() // 2, 14))
            
            # Handheld button references only
            footer_str = "[D-PAD ◄ / ►: TURN PAGES]    [B BUTTON: EXIT TO GAME]"
            f_surf = self.font_footer.render(footer_str, True, (170, 175, 180))
            screen.blit(f_surf, (SCREEN_WIDTH // 2 - f_surf.get_width() // 2, 448))
        else:
            title = self.font_header.render("INSTRUCTION MANUAL NOT FOUND", True, (255, 90, 80))
            msg1 = self.font_footer.render("To view the authentic 12-page game booklet in-game:", True, (230, 230, 230))
            msg2 = self.font_footer.render("1. Download the manual image from Lucas Pope's itch.io page", True, (180, 185, 190))
            msg3 = self.font_footer.render("2. Place it as 'manual.png' in the 'gamedata/' directory", True, (180, 185, 190))
            msg4 = self.font_footer.render("[PRESS B BUTTON OR START TO RETURN]", True, (140, 145, 150))
            
            screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 120))
            screen.blit(msg1, (SCREEN_WIDTH // 2 - msg1.get_width() // 2, 180))
            screen.blit(msg2, (SCREEN_WIDTH // 2 - msg2.get_width() // 2, 220))
            screen.blit(msg3, (SCREEN_WIDTH // 2 - msg3.get_width() // 2, 250))
            screen.blit(msg4, (SCREEN_WIDTH // 2 - msg4.get_width() // 2, 330))


# ---------------------------------------------------------------------------
# Controls Guide Screen (Tailored for R36S Console)
# ---------------------------------------------------------------------------
class ControlsScreen:
    def __init__(self):
        pygame.font.init()
        self.font_title = pygame.font.SysFont('Arial', 24, bold=True)
        self.font_sec = pygame.font.SysFont('Arial', 16, bold=True)
        self.font_lbl = pygame.font.SysFont('Arial', 15)
        self.font_btn = pygame.font.SysFont('Arial', 15, bold=True)
        self.font_hint = pygame.font.SysFont('Arial', 14)

    def render(self, screen):
        screen.fill(BACKDROP_COLOR)

        # Title
        t_surf = self.font_title.render("R36S CONTROLS GUIDE", True, (255, 215, 0))
        screen.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 26))

        # Section 1: Gameplay Controls
        s1 = self.font_sec.render("GAMEPLAY CONTROLS", True, (240, 240, 240))
        screen.blit(s1, (60, 76))
        pygame.draw.line(screen, (70, 75, 80), (60, 98), (580, 98), 1)

        game_controls = [
            ("MOVE ROOMS", "D-Pad Left / Right", "Walk through door to adjacent room"),
            ("STAIRS / CLIMB", "D-Pad Up  or  X Button", "Climb up or down floors"),
            ("SEARCH ROOM", "D-Pad Down  or  B Button", "Search furniture & cycle objects"),
            ("PAUSE MENU", "START Button", "Pause game & adjust display/sound"),
            ("MANUAL", "SELECT Button", "Open 12-page manual (freezes game)"),
        ]

        y = 108
        for name, btn, desc in game_controls:
            n_surf = self.font_btn.render(name, True, (255, 235, 120))
            b_surf = self.font_btn.render(btn, True, (255, 255, 255))
            d_surf = self.font_lbl.render(f"- {desc}", True, (170, 175, 180))
            screen.blit(n_surf, (65, y))
            screen.blit(b_surf, (240, y))
            screen.blit(d_surf, (65, y + 20))
            y += 42

        # Section 2: Shortcuts & Settings
        y += 4
        s2 = self.font_sec.render("SHORTCUTS & SETTINGS", True, (240, 240, 240))
        screen.blit(s2, (60, y))
        pygame.draw.line(screen, (70, 75, 80), (60, y + 22), (580, y + 22), 1)

        y += 30
        shortcuts = [
            ("SELECT + START", "Universal PortMaster Quick Exit"),
            ("DISPLAY & SOUND", "Framed Bezel, Glare, Ghosting & Sound in Pause Menu"),
        ]

        for btn, desc in shortcuts:
            b_surf = self.font_btn.render(btn, True, (140, 220, 255))
            d_surf = self.font_lbl.render(desc, True, (210, 215, 220))
            screen.blit(b_surf, (65, y))
            screen.blit(d_surf, (240, y))
            y += 24

        # Footer
        hint = self.font_hint.render("[PRESS B BUTTON OR START TO RETURN]", True, (160, 165, 170))
        screen.blit(hint, (SCREEN_WIDTH // 2 - hint.get_width() // 2, 450))


# ---------------------------------------------------------------------------
# Headless Game Engine Subprocess Bridge
# ---------------------------------------------------------------------------
class EngineBridge:
    def __init__(self, engine_js_path, moida_js_path=None):
        self.proc = None
        self.engine_js_path = engine_js_path
        self.moida_js_path = moida_js_path
        self._start_process()

    def _start_process(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
        candidates = [
            os.path.join(base_dir, 'bin', 'node.exe' if sys.platform == 'win32' else 'node'),
            os.path.join(base_dir, 'bin', 'qjs.exe' if sys.platform == 'win32' else 'qjs'),
            'node',
            'nodejs',
            'qjs'
        ]
        
        runner_bin = None
        for cand in candidates:
            if os.path.isfile(cand):
                runner_bin = cand
                break
            elif shutil.which(cand):
                runner_bin = cand
                break
                
        if not runner_bin:
            raise RuntimeError("No JavaScript runner found (checked bin/node, node, nodejs, qjs).")

        cmd = [runner_bin, self.engine_js_path]
        if self.moida_js_path:
            cmd.append(self.moida_js_path)

        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=base_dir,
            bufsize=1
        )
        
        ready = self.proc.stdout.readline().strip()
        if 'READY' not in ready:
            err = self.proc.stderr.read()
            raise RuntimeError(f"Engine failed to initialize. Output: {ready}. Errors: {err}")

    def tick(self, b_stairs, b_search, b_left, b_right):
        line = f"{1 if b_stairs else 0} {1 if b_search else 0} {1 if b_left else 0} {1 if b_right else 0}\n"
        self.proc.stdin.write(line)
        self.proc.stdin.flush()
        
        resp = self.proc.stdout.readline().strip()
        if not resp:
            return 100, 0.0, 0, []
            
        parts = resp.split()
        delay_ms = int(parts[0])
        beeper_hz = float(parts[1])
        beeper_dur = int(parts[2])
        words = [int(x) for x in parts[3:]]
        return delay_ms, beeper_hz, beeper_dur, words

    def close(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write("QUIT\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=1.0)
            except Exception:
                self.proc.kill()


# ---------------------------------------------------------------------------
# Pause & Options Menu
# ---------------------------------------------------------------------------
class PauseMenu:
    def __init__(self):
        self.selected_idx = 0
        self.items = [
            "Resume Game",
            "Controls Guide",
            "Instruction Manual",
            "Display Mode",
            "Ghost Segments",
            "Glass Glare",
            "Sound",
            "Quit Game"
        ]
        self.font_title = pygame.font.SysFont('Arial', 24, bold=True)
        self.font_item = pygame.font.SysFont('Arial', 18, bold=True)
        self.font_hint = pygame.font.SysFont('Arial', 14)

    def up(self):
        self.selected_idx = (self.selected_idx - 1 + len(self.items)) % len(self.items)

    def down(self):
        self.selected_idx = (self.selected_idx + 1) % len(self.items)

    def render(self, screen, mode_bezel, ghost_mode, glass_mode, sound_enabled):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 12, 14, 215))
        screen.blit(overlay, (0, 0))

        t_surf = self.font_title.render("PAUSED", True, (240, 240, 240))
        screen.blit(t_surf, (SCREEN_WIDTH // 2 - t_surf.get_width() // 2, 48))

        y_start = 108
        ghost_names = ["Off (Clean)", "Faint", "Vintage"]
        glass_names = ["Off", "Subtle", "Vintage"]
        
        for i, item in enumerate(self.items):
            is_sel = (i == self.selected_idx)
            color = (255, 215, 0) if is_sel else (210, 215, 220)
            
            display_text = item
            if item == "Display Mode":
                display_text = f"Display: < {'Framed Bezel' if mode_bezel else 'Fullscreen LCD'} >"
            elif item == "Ghost Segments":
                display_text = f"Ghost Segments: < {ghost_names[ghost_mode]} >"
            elif item == "Glass Glare":
                display_text = f"Glass Glare: < {glass_names[glass_mode]} >"
            elif item == "Sound":
                display_text = f"Sound: < {'ON' if sound_enabled else 'MUTED'} >"
                
            prefix = "► " if is_sel else "   "
            item_surf = self.font_item.render(prefix + display_text, True, color)
            screen.blit(item_surf, (SCREEN_WIDTH // 2 - 170, y_start + i * 36))

        # Handheld button references only
        hint_surf = self.font_hint.render("[D-PAD: NAVIGATE / ADJUST]    [B BUTTON: SELECT]    [START: RESUME]", True, (150, 155, 160))
        screen.blit(hint_surf, (SCREEN_WIDTH // 2 - hint_surf.get_width() // 2, 442))


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
def main():
    pygame.init()

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Moida Mansion")
    clock = pygame.time.Clock()

    # Asset Paths (Supports standard names and raw itch.io download names)
    lcd_assets_path = find_asset('lcd_assets.json')
    engine_js_path = find_asset('engine.js')
    moida_js_path = find_asset(['moida.js', 'moida*.js'])
    manual_path = find_asset(['manual.png', '02wPJo*.png', 'manual*.png'])
    bezel_path = find_asset(['hardware.jpg', 'hardware*.jpg', 'hardware_jpg*.jpg', 'bezel.png', 'case.png', 'fBYlLE*.png', 'case*.png'])
    glass_path = find_asset(['glass.jpg', 'glass*.jpg', 'glass_jpg*.jpg'])

    # Verify critical components
    if not lcd_assets_path or not engine_js_path or not moida_js_path:
        font_big = pygame.font.SysFont('Arial', 22, bold=True)
        font_sm = pygame.font.SysFont('Arial', 16)
        running = True
        while running:
            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.KEYDOWN, pygame.JOYBUTTONDOWN):
                    running = False
            screen.fill((20, 22, 26))
            t1 = font_big.render("MOIDA MANSION - REQUIRED ASSETS MISSING", True, (255, 80, 80))
            t2 = font_sm.render("Please ensure the following files exist in this folder or 'gamedata/':", True, (220, 220, 220))
            
            files = [
                ("lcd_assets.json", lcd_assets_path is not None),
                ("engine.js", engine_js_path is not None),
                ("moida.js (from itch.io)", moida_js_path is not None),
                ("manual.png (optional booklet)", manual_path is not None),
            ]
            y = 170
            for name, ok in files:
                status = "[FOUND]" if ok else "[MISSING]"
                col = (100, 240, 100) if ok else (240, 80, 80)
                surf = font_sm.render(f"{status:<10}  {name}", True, col)
                screen.blit(surf, (SCREEN_WIDTH // 2 - 180, y))
                y += 32
                
            t3 = font_sm.render("[PRESS ANY BUTTON TO EXIT]", True, (150, 150, 150))
            screen.blit(t1, (SCREEN_WIDTH // 2 - t1.get_width() // 2, 70))
            screen.blit(t2, (SCREEN_WIDTH // 2 - t2.get_width() // 2, 120))
            screen.blit(t3, (SCREEN_WIDTH // 2 - t3.get_width() // 2, 400))
            pygame.display.flip()
            clock.tick(15)
        pygame.quit()
        sys.exit(1)

    # Subsystems
    renderer = LCDRenderer(lcd_assets_path, bezel_path, glass_path)
    audio = PiezoSynthesizer()
    manual = ManualViewer(manual_path)
    controls_screen = ControlsScreen()
    menu = PauseMenu()
    
    try:
        engine = EngineBridge(engine_js_path, moida_js_path)
    except Exception as e:
        print(f"Failed to start engine: {e}", file=sys.stderr)
        pygame.quit()
        sys.exit(1)

    # Runtime Settings
    state = STATE_GAME
    mode_bezel = True if bezel_path else False
    ghost_mode = 0  # 0: Off (Clean, original), 1: Faint, 2: Vintage
    glass_mode = 0  # 0: Off, 1: Subtle, 2: Vintage
    sound_enabled = True

    # Button States (0: Stairs, 1: Search, 2: Move Left, 3: Move Right)
    btn_stairs = False
    btn_search = False
    btn_left = False
    btn_right = False

    # Timing
    current_delay_ms = 100
    next_tick_time = time.time()
    active_indices = []

    # Menu Action Helpers
    def select_menu_item():
        nonlocal state, mode_bezel, ghost_mode, glass_mode, sound_enabled, running, next_tick_time
        sel = menu.items[menu.selected_idx]
        if sel == "Resume Game":
            state = STATE_GAME
            next_tick_time = time.time() + (current_delay_ms / 1000.0)
        elif sel == "Controls Guide":
            state = STATE_CONTROLS
        elif sel == "Instruction Manual":
            state = STATE_MANUAL
            audio.play_tone(0, 0)
        elif sel == "Display Mode":
            mode_bezel = not mode_bezel
        elif sel == "Ghost Segments":
            ghost_mode = (ghost_mode + 1) % 3
        elif sel == "Glass Glare":
            glass_mode = (glass_mode + 1) % 3
        elif sel == "Sound":
            sound_enabled = not sound_enabled
            audio.enabled = sound_enabled
        elif sel == "Quit Game":
            running = False

    def adjust_menu_setting(direction):
        nonlocal mode_bezel, ghost_mode, glass_mode, sound_enabled
        sel = menu.items[menu.selected_idx]
        if sel == "Display Mode":
            mode_bezel = not mode_bezel
        elif sel == "Ghost Segments":
            ghost_mode = (ghost_mode + direction) % 3
        elif sel == "Glass Glare":
            glass_mode = (glass_mode + direction) % 3
        elif sel == "Sound":
            sound_enabled = not sound_enabled
            audio.enabled = sound_enabled

    # Main Event & Game Loop
    running = True
    while running:
        current_time = time.time()

        # -------------------------------------------------------------------
        # Event Handling (Driven cleanly by gptokeyb on handheld)
        # -------------------------------------------------------------------
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break

            if event.type == pygame.KEYDOWN:
                k = event.key

                # Emergency quick exit combo (Select + Start)
                if k in (pygame.K_p, pygame.K_m):
                    pressed = pygame.key.get_pressed()
                    if pressed[pygame.K_p] and pressed[pygame.K_m]:
                        running = False
                        break

                # -----------------------------------------------------------
                # State: Active Gameplay
                # -----------------------------------------------------------
                if state == STATE_GAME:
                    # D-Pad / Analog Left & Right: Move rooms
                    if k in (pygame.K_LEFT, pygame.K_a):
                        btn_left = True
                    elif k in (pygame.K_RIGHT, pygame.K_d):
                        btn_right = True
                    # D-Pad Up or X Button: Move through floors (Stairs)
                    elif k in (pygame.K_UP, pygame.K_w, pygame.K_x):
                        btn_stairs = True
                    # D-Pad Down or B Button: Search furniture & cycle items
                    elif k in (pygame.K_DOWN, pygame.K_s, pygame.K_b):
                        btn_search = True
                    # START Button: Open Pause Menu (Game Paused)
                    elif k in (pygame.K_p, pygame.K_ESCAPE):
                        state = STATE_MENU
                        audio.play_tone(0, 0)
                    # SELECT Button: Open Instruction Manual (Game Paused)
                    elif k == pygame.K_m:
                        state = STATE_MANUAL
                        audio.play_tone(0, 0)
                    # Y, A, L1, R1, L2, R2: Do nothing

                # -----------------------------------------------------------
                # State: Pause Menu
                # -----------------------------------------------------------
                elif state == STATE_MENU:
                    # D-Pad Up / Down: Navigate options
                    if k in (pygame.K_UP, pygame.K_w):
                        menu.up()
                    elif k in (pygame.K_DOWN, pygame.K_s):
                        menu.down()
                    # D-Pad Left / Right: Adjust highlighted setting
                    elif k in (pygame.K_LEFT, pygame.K_a):
                        adjust_menu_setting(-1)
                    elif k in (pygame.K_RIGHT, pygame.K_d):
                        adjust_menu_setting(1)
                    # B Button: Select / Confirm highlighted item
                    elif k in (pygame.K_b, pygame.K_RETURN, pygame.K_SPACE):
                        select_menu_item()
                    # START Button: Resume game
                    elif k in (pygame.K_p, pygame.K_ESCAPE):
                        state = STATE_GAME
                        next_tick_time = time.time() + (current_delay_ms / 1000.0)
                    # SELECT, X, Y, A, Shoulders: Do nothing

                # -----------------------------------------------------------
                # State: Instruction Manual
                # -----------------------------------------------------------
                elif state == STATE_MANUAL:
                    # D-Pad Right: Next page in sequential order
                    if k in (pygame.K_RIGHT, pygame.K_d):
                        manual.next_page()
                    # D-Pad Left: Previous page in sequential order
                    elif k in (pygame.K_LEFT, pygame.K_a):
                        manual.prev_page()
                    # B Button or START / SELECT: Exit back to game
                    elif k in (pygame.K_b, pygame.K_p, pygame.K_m, pygame.K_ESCAPE):
                        state = STATE_GAME
                        next_tick_time = time.time() + (current_delay_ms / 1000.0)

                # -----------------------------------------------------------
                # State: Controls Guide
                # -----------------------------------------------------------
                elif state == STATE_CONTROLS:
                    # B Button or START: Return to Pause Menu
                    if k in (pygame.K_b, pygame.K_p, pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                        state = STATE_MENU

            elif event.type == pygame.KEYUP:
                k = event.key
                if state == STATE_GAME:
                    if k in (pygame.K_LEFT, pygame.K_a):
                        btn_left = False
                    elif k in (pygame.K_RIGHT, pygame.K_d):
                        btn_right = False
                    elif k in (pygame.K_UP, pygame.K_w, pygame.K_x):
                        btn_stairs = False
                    elif k in (pygame.K_DOWN, pygame.K_s, pygame.K_b):
                        btn_search = False

        # -------------------------------------------------------------------
        # Engine Simulation Step
        # -------------------------------------------------------------------
        if state == STATE_GAME and current_time >= next_tick_time:
            delay_ms, beeper_hz, beeper_dur, words = engine.tick(
                btn_stairs, btn_search, btn_left, btn_right
            )
            
            if sound_enabled and beeper_hz > 0:
                audio.play_tone(beeper_hz, beeper_dur if beeper_dur > 0 else delay_ms)
                
            if words:
                active_indices = []
                for i in range(renderer.num_segments):
                    word_idx = i // 32
                    bit_idx = i % 32
                    if word_idx < len(words) and (words[word_idx] & (1 << bit_idx)) != 0:
                        active_indices.append(i)

            current_delay_ms = delay_ms if delay_ms > 0 else 100
            next_tick_time = current_time + (current_delay_ms / 1000.0)

        # -------------------------------------------------------------------
        # Rendering
        # -------------------------------------------------------------------
        if state == STATE_GAME:
            renderer.render(screen, active_indices, mode_bezel, glass_mode, ghost_mode)
        elif state == STATE_MANUAL:
            manual.render(screen)
        elif state == STATE_CONTROLS:
            controls_screen.render(screen)
        elif state == STATE_MENU:
            renderer.render(screen, active_indices, mode_bezel, glass_mode, ghost_mode)
            menu.render(screen, mode_bezel, ghost_mode, glass_mode, sound_enabled)

        pygame.display.flip()
        clock.tick(FPS)

    # Clean Shutdown
    engine.close()
    pygame.quit()
    sys.exit(0)


if __name__ == '__main__':
    main()
