# Robot Touch Alignment (RTA)

System to align the robot z-axis to interact with the cellphone.

## ArUco Marker Placement Map

The app places ArUco markers (`tag36h11` family) on screen based on the selected device profile.  
Profile is set via ADB:

```bash
adb shell am start -n com.example.rta/.MainActivity --es device_type <profile>
```

Available profiles: `flat`, `foldable`, `one`, `two`, `three`, `six`, `seven`, `eight`.

---

### Profiles with ≤6 markers — Diagonal Placement

Markers are placed in a diagonal Z-order across the full screen.

#### `one` (1 marker)

| Tag  | Position    |
|------|-------------|
| tag1 | ↖ Top-Left |

#### `two` (2 markers)

| Tag  | Position       |
|------|----------------|
| tag1 | ↖ Top-Left     |
| tag2 | ↘ Bottom-Right |

#### `three` (3 markers)

| Tag  | Position       |
|------|----------------|
| tag1 | ↖ Top-Left     |
| tag2 | ↘ Bottom-Right |
| tag3 | ↙ Bottom-Left  |

#### `flat` (4 markers)

| Tag  | Position       |
|------|----------------|
| tag1 | ↖ Top-Left     |
| tag2 | ↘ Bottom-Right |
| tag3 | ↙ Bottom-Left  |
| tag4 | ↗ Top-Right    |

```
┌──────────────────┐
│ tag1        tag4 │
│                  │
│                  │
│                  │
│ tag3        tag2 │
└──────────────────┘
```

#### `six` (6 markers)

| Tag  | Position        |
|------|-----------------|
| tag1 | ↖ Top-Left      |
| tag2 | ↘ Bottom-Right  |
| tag3 | ↙ Bottom-Left   |
| tag4 | ↗ Top-Right     |
| tag5 | ← Center-Left   |
| tag6 | → Center-Right  |

```
┌──────────────────┐
│ tag1        tag4 │
│                  │
│ tag5        tag6 │
│                  │
│ tag3        tag2 │
└──────────────────┘
```

---

### Profiles with >6 markers — Foldable (Split Screen)

The screen is divided into **two equal halves** (simulating a foldable's two displays).  
- **Top half**: first 4 markers at the 4 corners (rectangle).  
- **Bottom half**: remaining markers fill corners in order: Bottom-Left → Bottom-Right → Top-Left → Top-Right.

#### `seven` (7 markers)

**Top half** — 4 corners (rectangle closed):

| Tag  | Position                |
|------|-------------------------|
| tag1 | ↖ Top-half Top-Left     |
| tag2 | ↗ Top-half Top-Right    |
| tag3 | ↙ Top-half Bottom-Left  |
| tag4 | ↘ Top-half Bottom-Right |

**Bottom half** — 3 corners (Top-Right open):

| Tag  | Position                  |
|------|---------------------------|
| tag5 | ↙ Bottom-half Bottom-Left  |
| tag6 | ↘ Bottom-half Bottom-Right |
| tag7 | ↖ Bottom-half Top-Left     |

```
 Top Half               Bottom Half
┌──────────────────┐   ┌──────────────────┐
│ tag1        tag2 │   │ tag7             │
│                  │   │                  │
│ tag3        tag4 │   │ tag5        tag6 │
└──────────────────┘   └──────────────────┘
```

#### `eight` / `foldable` (8 markers)

**Top half** — 4 corners (rectangle closed):

| Tag  | Position                |
|------|-------------------------|
| tag1 | ↖ Top-half Top-Left     |
| tag2 | ↗ Top-half Top-Right    |
| tag3 | ↙ Top-half Bottom-Left  |
| tag4 | ↘ Top-half Bottom-Right |

**Bottom half** — 4 corners (rectangle closed):

| Tag  | Position                   |
|------|----------------------------|
| tag5 | ↙ Bottom-half Bottom-Left  |
| tag6 | ↘ Bottom-half Bottom-Right |
| tag7 | ↖ Bottom-half Top-Left     |
| tag8 | ↗ Bottom-half Top-Right    |

```
 Top Half               Bottom Half
┌──────────────────┐   ┌──────────────────┐
│ tag1        tag2 │   │ tag7        tag8 │
│                  │   │                  │
│ tag3        tag4 │   │ tag5        tag6 │
└──────────────────┘   └──────────────────┘
```

---

### Success / Failure Screens

| Screen  | Marker | Position   |
|---------|--------|------------|
| ✅ Success | tag14  | Centered |
| ❌ Failure | tag15  | Centered |
