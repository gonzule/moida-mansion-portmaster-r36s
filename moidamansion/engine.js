// engine.js - Headless Moida Mansion engine bridge
const fs = require('fs');
const readline = require('readline');
const vm = require('vm');

// Find and load moida.js
let moidaPath = process.argv[2];
if (!moidaPath || !fs.existsSync(moidaPath)) {
    const candidates = [
        'moida.js',
        'gamedata/moida.js',
        'Moida Mansion_files/moida_i9Qw.js'
    ];
    if (fs.existsSync('gamedata')) {
        try {
            const files = fs.readdirSync('gamedata');
            for (const f of files) {
                if (f.startsWith('moida') && f.endsWith('.js')) {
                    candidates.push('gamedata/' + f);
                }
            }
        } catch (e) {}
    }
    moidaPath = candidates.find(p => fs.existsSync(p));
}

if (!moidaPath || !fs.existsSync(moidaPath)) {
    console.error('ERROR: moida.js not found in current directory or gamedata/');
    process.exit(1);
}

const js = fs.readFileSync(moidaPath, 'utf8');

const dummyElem = {
    style: {},
    classList: { contains: () => false, remove: () => {}, add: () => {} },
    appendChild: () => {},
    addEventListener: () => {}
};

const sandbox = {
    console: { log: () => {}, error: () => {}, warn: () => {} },
    Math: Math,
    Int32Array: Int32Array,
    Uint16Array: Uint16Array,
    Uint8Array: Uint8Array,
    Float64Array: Float64Array,
    Howl: function() { return { play: () => {} }; },
    Howler: { volume: () => {} },
    document: {
        getElementById: () => dummyElem,
        createElement: () => ({ content: { firstChild: dummyElem }, style: {}, addEventListener: () => {} }),
        addEventListener: () => {},
        hasFocus: () => true
    },
    window: {
        addEventListener: () => {},
        getComputedStyle: () => ({ getPropertyValue: () => '100px', width: '100px', height: '100px' })
    },
    setTimeout: () => {},
    clearTimeout: () => {},
    AudioContext: function() {
        return {
            createOscillator: () => ({ connect: () => {}, start: () => {}, stop: () => {}, type: '' }),
            createGain: () => ({ connect: () => {}, gain: { value: 0 } }),
            destination: {}
        };
    }
};

vm.createContext(sandbox);
vm.runInContext(js, sandbox);

const tickFunc = sandbox.gameConfig_721420506[0].tickFunc;
if (!tickFunc) {
    console.error('ERROR: tickFunc not found');
    process.exit(1);
}

// Ready signal
process.stdout.write('READY\n');

// Readline from stdin
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

let curButtons = {};
let preButtons = {};

rl.on('line', (line) => {
    line = line.trim();
    if (line === 'QUIT') {
        process.exit(0);
    }
    
    // Line format: "b0 b1 b2 b3" (0 or 1 for each button)
    const parts = line.split(/\s+/).map(Number);
    curButtons = {};
    for (let i = 0; i < 4; i++) {
        if (parts[i]) {
            curButtons[i] = true;
        }
    }
    
    const gameIn = {
        curButtonIds: curButtons,
        preButtonIds: preButtons
    };
    
    const out = tickFunc(gameIn);
    preButtons = Object.assign({}, curButtons);
    
    // Serialize output: "delay beeperHz beeperDuration data0 data1 ... data19"
    const words = Array.from(out.spriteState.data);
    const dur = out.beeperDurationInMs || 0;
    const response = `${out.wakeAfterDelayInMs} ${out.beeperHz} ${dur} ` + words.join(' ');
    process.stdout.write(response + '\n');
});

