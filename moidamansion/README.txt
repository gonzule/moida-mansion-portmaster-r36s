=============================================================================
MOIDA MANSION - PORT FOR R36S & RETRO HANDHELDS (PORTMASTER)
Original Game created by Lucas Pope (https://dukope.itch.io/moida-mansion)
Ported by Community for PortMaster & Pygame-CE
=============================================================================

This port allows you to experience Lucas Pope's retro LCD handheld adventure 
game "Moida Mansion" natively on your retro handheld console (such as the 
R36S running ArkOS) or PC!

-----------------------------------------------------------------------------
1. USER-PROVIDED GAME FILES (COPYRIGHT & LEGAL)
-----------------------------------------------------------------------------
To respect the copyright of the original creator (Lucas Pope), proprietary 
game logic and original booklet artwork are NOT bundled with this port. 

You must supply two files from the original game:
1. `moida.js` (The game code)
2. `manual.png` (The 12-page instruction manual sheet - optional but recommended)

HOW TO GET THEM:
1. Go to https://dukope.itch.io/moida-mansion in your web browser.
2. Open the page source or developer tools (F12 -> Network -> Fetch/JS/Img).
3. Save the main game script as `moida.js` and put it in the `gamedata/` folder.
   (Or save the complete webpage: the file is named `moida_*.js`).
4. Download the manual image (the booklet matrix image from the page description)
   and save it as `manual.png` in the `gamedata/` folder.

-----------------------------------------------------------------------------
2. HOW TO TEST ON PC (WINDOWS / LINUX / MAC)
-----------------------------------------------------------------------------
Prerequisites:
- Python 3.9+ with pygame-ce installed:
    pip install pygame-ce
- Node.js (any LTS version from https://nodejs.org)

To launch the game:
    python main.py

Controls on PC:
- D-Pad / Arrows / WASD : Mode (Up), View (Down/Enter), Deny (Left), Approve (Right)
- Action Buttons        : Enter / Space (View/Interact), X (Mode), A/D (Left/Right)
- Tab or F1             : Toggle between Framed Bezel and Fullscreen LCD mode
- L or F2               : Toggle vintage LCD glass glare reflection (Off / Subtle / Vintage)
- F3                    : Mute / Unmute sound
- M or F4               : Open / Close the 12-Page Instruction Manual
- Esc or P              : Open In-Game Pause / Options Menu

-----------------------------------------------------------------------------
3. HOW TO INSTALL ON R36S (PORTMASTER)
-----------------------------------------------------------------------------
Folder Structure on your R36S MicroSD card (`roms/ports/` or `ports/`):

roms/ports/
├── Moida Mansion.sh
└── moidamansion/
    ├── main.py
    ├── engine.js
    ├── lcd_assets.json
    ├── bezel.png
    ├── glass.jpg
    ├── moidamansion.gptk
    ├── port.json
    ├── gameinfo.xml
    ├── screenshot.png
    ├── cover.png
    └── gamedata/
        ├── moida.js       <-- (Supplied by you)
        └── manual.png     <-- (Supplied by you)

Controls on R36S:
- D-Pad Up / X Button    : MODE / UP
- D-Pad Down / Y Button  : VIEW / INTERACT (Enter)
- D-Pad Left / B Button  : DENY / LEFT
- D-Pad Right / A Button : APPROVE / RIGHT
- L1                     : Toggle Framed Bezel vs Fullscreen LCD
- R1                     : Toggle Vintage Glass Glare
- L2 / R2 / Select       : Open 12-Page Sliced Instruction Manual
- Start                  : Pause Menu / Options
- Select + Start         : Universal PortMaster Quick Exit

Enjoy solving the mystery of Moida Mansion on your handheld!
=============================================================================
