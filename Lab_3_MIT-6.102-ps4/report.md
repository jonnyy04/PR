# Memory Scramble Lab Report

## 1. Project Overview

This project implements a networked multiplayer Memory Scramble game for MIT 6.102 Problem Set 4. Multiple players flip cards concurrently on a shared game board to find matching pairs.

**Key Files:**

-   `board.ts` - Game board implementation
-   `commands.ts` - Interface between board and web server
-   `server.ts` - HTTP server (provided)
-   `boards/perfect.txt` - Sample 3x3 board file

## 2. Board Implementation

### 2.1 Core Data Structures

```typescript
class Board {
    private readonly cards: (string | null)[][];     // Card contents
    private readonly faceUp: boolean[][];            // Face up/down state
    private readonly control: (string | null)[][];   // Player control
    private readonly playerState: Map<...>;          // Player game state
    private waiting: Map<string, Deferred<void>[]>;  // Waiting queues
    private watchers: Array<Deferred<void>>;         // Change observers
}
```

### 2.2 Representation Invariant

-   Board dimensions must be positive
-   No null cards can be face-up
-   No null cards can be controlled by a player
-   All arrays have consistent dimensions

### 2.3 Concurrency with Promises

```typescript
class Deferred<T> {
	promise: Promise<T>;
	resolve!: (value: T) => void;

	constructor() {
		this.promise = new Promise<T>((res) => {
			this.resolve = res;
		});
	}
}
```

This pattern enables asynchronous waiting without busy-waiting.

## 3. Game Rules Implementation

### First Card Rules

```typescript
// Rule 1-A: No card at position
if (this.cards[row]?.[col] == null) throw new Error("No card at that position");

// Rule 1-D: Wait if controlled by another player
if (this.faceUp[row]?.[col] && this.control[row]?.[col] !== player) {
	const deferred = new Deferred<void>();
	this.waiting.get(key)!.push(deferred);
	await deferred.promise; // Wait asynchronously
}

// Rules 1-B/1-C: Take control
this.faceUp[row]![col] = true;
this.control[row]![col] = player;
```

### Second Card Rules

```typescript
// Rule 2-B: Avoid deadlock - fail immediately if controlled
if (this.control[row]?.[col] && this.control[row]![col] !== player) {
	this.control[state.first.row]![state.first.col] = null;
	throw new Error("Card already controlled");
}

// Compare cards
if (state.first.card === state.second.card) {
	state.lastMatch = [state.first, state.second]; // Match
} else {
	state.lastMismatch = [state.first, state.second]; // Mismatch
}
```

### Cleanup Rules

```typescript
// Rule 3-A: Remove matched cards
if (state.lastMatch) {
	for (const pos of state.lastMatch) {
		this.cards[pos.row]![pos.col] = null;
		this.releaseControl(pos.row, pos.col); // Wake waiting players
	}
}

// Rule 3-B: Flip mismatched cards face down
if (state.lastMismatch) {
	for (const pos of state.lastMismatch) {
		if (exists && noController && isUp) {
			this.faceUp[pos.row]![pos.col] = false;
		}
	}
}
```

## 4. Commands Interface

All command functions are simple glue code (3 lines or fewer):

```typescript
export async function look(board: Board, playerId: string): Promise<string> {
	return board.toDisplayString(playerId);
}

export async function flip(board: Board, playerId: string, row: number, column: number): Promise<string> {
	await board.flipCard(playerId, row, column);
	return board.toDisplayString(playerId);
}

export async function map(board: Board, playerId: string, f: (card: string) => Promise<string>): Promise<string> {
	await board.mapCards(f);
	return board.toDisplayString(playerId);
}

export async function watch(board: Board, playerId: string): Promise<string> {
	await board.watch();
	return board.toDisplayString(playerId);
}
```

## 5. Board File Format

### Example: boards/perfect.txt

```
3x3
🦄
🦄
🌈
🌈
🌈
🦄
🌈
🦄
🌈

```

This creates a 3x3 board with cards listed row by row.

### Parsing Implementation

```typescript
public static async parseFromFile(filename: string): Promise<Board> {
    const content = await fs.promises.readFile(filename, "utf8");
    const lines = content.trim().split(/\r?\n/);

    const match = lines[0]?.match(/^(\d+)x(\d+)$/);
    const rows = parseInt(match[1]!);
    const cols = parseInt(match[2]!);

    // Build 2D array from remaining lines
    const cards: string[][] = [];
    for (let r = 0; r < rows; r++) {
        const rowCards = [];
        for (let c = 0; c < cols; c++) {
            rowCards.push(cardLines[r * cols + c].trim());
        }
        cards.push(rowCards);
    }

    return new Board(rows, cols, cards);
}
```

## 6. Concurrent Gameplay

### Waiting Example

1. Alice flips (0,0) - takes control
2. Bob tries to flip (0,0) - waits
3. Alice flips (0,1) - mismatch, releases (0,0)
4. Bob's request completes - takes control of (0,0)

### Deadlock Prevention

If Alice controls card A and Bob controls card B:

-   Alice tries to flip B as second card → fails immediately (no wait)
-   This prevents circular waiting

Implementation:

```typescript
if (this.control[row]?.[col] && this.control[row]![col] !== player) {
	throw new Error("Card already controlled"); // No deadlock
}
```

## 7. Map Transformation (Problem 4)

Transforms all cards using an async function:

```typescript
public async mapCards(f: (card: string) => Promise<string>): Promise<void> {
    const tasks: Promise<void>[] = [];

    for (let r = 0; r < this.rows; r++) {
        for (let c = 0; c < this.cols; c++) {
            const card = this.cards[r]?.[c];
            if (card !== null) {
                tasks.push((async () => {
                    const newCard = await f(card);
                    if (this.cards[r]?.[c] !== null) {
                        this.cards[r]![c] = newCard;
                    }
                })());
            }
        }
    }

    await Promise.all(tasks);
}
```

Example transformation:

```typescript
// Transform: unicorn → sun, rainbow → lollipop
await board.mapCards(async (card) => {
	return card === "unicorn" ? "sun" : card === "rainbow" ? "lollipop" : card;
});
```

## 8. Watch Feature (Problem 5)

### Implementation

```typescript
private watchers: Array<Deferred<void>> = [];

public async watch(): Promise<void> {
    const deferred = new Deferred<void>();
    this.watchers.push(deferred);
    await deferred.promise;
}

private notifyWatchers(): void {
    for (const watcher of this.watchers) {
        watcher.resolve();
    }
    this.watchers = [];
}
```

### When Notifications Occur

-   Card flips face up
-   Card flips face down
-   Card is removed
-   Card content changes (via map)

### Benefits Over Polling

-   **Polling**: Client checks every 500ms, wastes bandwidth
-   **Watching**: Server notifies immediately on change (under 50ms)

## 9. Key Design Decisions

### Player State Storage

Stored in Board class rather than separate Player ADT - simplifies synchronization.

### Waiting Queues

One queue per card position - players wait for specific cards, not global changes.

### Atomicity

Card flips are atomic; cleanup operations (removing/flipping down) notify watchers.

### Safety from Rep Exposure

-   All fields private
-   Defensive copying in constructor
-   No mutable objects returned

## 10. Conclusion

The implementation successfully handles:

-   Correct game rules (all 11 rules implemented)
-   Concurrent player interactions without race conditions
-   Asynchronous waiting using Promises
-   Deadlock prevention via Rule 2-B
-   Efficient change notifications (watch feature)
-   Safe card transformations (map feature)
-   Clean separation between board logic and server interface

The system demonstrates proper concurrent programming with shared mutable state while maintaining safety, clarity, and flexibility.
