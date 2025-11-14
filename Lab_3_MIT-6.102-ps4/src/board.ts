/* Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
 * Redistribution of original or derived work requires permission of course staff.
 */

import assert from "node:assert";
import fs from "node:fs";

/**
 * A utility class that provides a way to resolve a Promise externally.
 *
 * This class wraps a Promise and exposes its resolve function, allowing you to
 * resolve the promise at any point in time outside of the promise constructor.
 *
 * @template T The type of value that the promise will resolve to.
 *
 * @example
 * ```typescript
 * const deferred = new Deferred<string>();
 *
 * // Later, you can resolve the promise
 * deferred.resolve("Hello World");
 *
 * // And access the promise
 * const result = await deferred.promise; // "Hello World"
 * ```
 */
class Deferred<T> {
	promise: Promise<T>;
	resolve!: (value: T) => void;

	constructor() {
		this.promise = new Promise<T>((res) => {
			this.resolve = res;
		});
	}
}

export class Board {
	private readonly rows: number;
	private readonly cols: number;
	private readonly cards: (string | null)[][];
	private readonly faceUp: boolean[][];
	private readonly control: (string | null)[][];
	private readonly playerState: Map<
		string,
		{
			first?: { row: number; col: number; card: string };
			second?: { row: number; col: number; card: string };
			lastMatch?: { row: number; col: number }[];
			lastMismatch?: { row: number; col: number }[];
		}
	> = new Map();

	// Players waiting to take control of a card
	private waiting: Map<string, Deferred<void>[]> = new Map();
	// Observers for board changes
	private watchers: Array<Deferred<void>> = [];

	constructor(rows: number, cols: number, cards: string[][]) {
		this.rows = rows;
		this.cols = cols;
		this.cards = cards.map((row) => row.slice());
		this.faceUp = Array.from({ length: rows }, () => Array<boolean>(cols).fill(false));
		this.control = Array.from({ length: rows }, () => Array<string | null>(cols).fill(null));
		this.checkRep();
	}

	/**
	 * Validates the internal representation invariants of the board instance.
	 * Invariants checked:
	 * - rows and cols are positive integers.
	 * - this.cards.length === this.rows.
	 * - Each row in this.cards is defined and has length this.cols.
	 * - For every cell (r, c):
	 *   - If the card is null (removed), then:
	 *     - faceUp[r][c] must be falsy (not true).
	 *     - control[r][c] must be null.
	 *   - If the card is undefined, an error is raised (missing data).
	 *   - If the card is non-null, faceUp[r][c] and control[r][c] must be defined.
	 *
	 * This method does not mutate state; it only observes arrays and throws
	 * when a contract is violated.
	 *
	 * Complexity: O(rows * cols).
	 *
	 * @private
	 * @throws {AssertionError} If basic size assertions (positive dimensions,
	 *         matching row counts and column counts) fail.
	 * @throws {Error} If per-cell consistency checks fail (e.g. a removed card
	 *         is marked face-up or has a controller, a cell is undefined, or
	 *         a present card lacks corresponding faceUp/control entries).
	 */
	private checkRep(): void {
		assert(this.rows > 0 && this.cols > 0, `Error: board must have positive dimensions, but has ${this.rows}x${this.cols}`);
		assert(this.cards.length === this.rows, `Error: number of rows in cards (${this.cards.length}) does not match rows (${this.rows})`);

		for (let i = 0; i < this.cards.length; i++) {
			const row = this.cards[i];
			assert(row !== undefined, `Error: row ${i} is undefined`);
			assert(row.length === this.cols, `Error: row ${i} has ${row.length} columns, but should have ${this.cols}`);
		}

		for (let r = 0; r < this.rows; r++) {
			for (let c = 0; c < this.cols; c++) {
				const card = this.cards[r]?.[c];
				const faceUp = this.faceUp[r]?.[c];
				const controller = this.control[r]?.[c];

				if (card === null && faceUp) {
					throw new Error(`Error: card (${r},${c}) has been removed (null), but faceUp[r][c] is TRUE.`);
				}
				if (card === null && controller !== null) {
					throw new Error(`Error: card (${r},${c}) is null, but control[r][c] = '${controller}'.`);
				}
				if (card === undefined) {
					throw new Error(`Error: card (${r},${c}) is undefined (perhaps missing in the cards array).`);
				}
				if (card !== null) {
					if (faceUp === undefined) throw new Error(`Error: faceUp[${r}][${c}] is undefined for an existing card.`);
					if (controller === undefined) throw new Error(`Error: control[${r}][${c}] is undefined for an existing card.`);
				}
			}
		}
	}

	/**
	 * Loads a board configuration from a file.
	 *
	 * The file format is:
	 * - Line 1: Board dimensions as "rowsxcols" (e.g., "2x2")
	 * - Lines 2+: One card per line, ordered left-to-right, top-to-bottom
	 *
	 * @param filename - Path to the board file
	 * @returns A Promise that resolves to a new Board instance
	 * @throws If the file is invalid, has incorrect dimensions, or missing cards
	 *
	 * @example
	 * ```typescript
	 * const board = await Board.parseFromFile("boards/game.txt");
	 * ```
	 */
	public static async parseFromFile(filename: string): Promise<Board> {
		const content: string = await fs.promises.readFile(filename, "utf8");
		const lines: string[] = content.trim().split(/\r?\n/);
		if (lines.length < 2) throw new Error("Invalid board file");

		const match = lines[0]?.match(/^(\d+)x(\d+)$/);
		if (!match) throw new Error("Invalid board size line");

		const rows = parseInt(match[1]!);
		const cols = parseInt(match[2]!);
		const expectedCards = rows * cols;
		const cardLines = lines.slice(1);

		if (cardLines.length !== expectedCards) throw new Error("Incorrect number of cards");

		const cards: string[][] = [];
		for (let r = 0; r < rows; r++) {
			const rowCards: string[] = [];
			for (let c = 0; c < cols; c++) {
				const idx = r * cols + c;
				const line = cardLines[idx];
				if (line === undefined) throw new Error("Missing card line");
				const card = line.trim();
				if (!card) throw new Error(`Empty card at position ${r},${c}`);
				rowCards.push(card);
			}
			cards.push(rowCards);
		}

		return new Board(rows, cols, cards);
	}

	public getRows(): number {
		return this.rows;
	}

	public getCols(): number {
		return this.cols;
	}

	public getCards(): (string | null)[][] {
		return this.cards;
	}

	public getFaceUp(): boolean[][] {
		return this.faceUp;
	}

	public getControl(): (string | null)[][] {
		return this.control;
	}

	private releaseControl(row: number, col: number) {
		const key = `${row},${col}`;
		const queue = this.waiting.get(key);
		if (queue && queue.length > 0) {
			const next = queue.shift()!;
			//console.log(`[releaseControl] Resolving waiter for ${key} (queue left: ${queue.length})`);
			next.resolve();
		}
	}

	/**
	 * Flips a card face-up and handles game logic for the Memory Scramble game.
	 *
	 * Behavior:
	 * - First card flip: Marks the card as controlled by the player
	 * - Second card flip: Compares with the first card
	 *   - If matching: Cards stay face-up (removed on next turn)
	 *   - If mismatched: Both cards flip back down on the next first-card flip
	 * - Waiting: If another player controls the card, this call waits until control is released
	 *
	 * @param player - The player ID attempting to flip the card
	 * @param row - Card row (0-indexed)
	 * @param col - Card column (0-indexed)
	 * @returns A Promise that resolves when the flip is complete
	 * @throws If coordinates are invalid, no card exists, or card is controlled by another player
	 *
	 * @example
	 * ```typescript
	 * await board.flipCard("player1", 0, 0);
	 * await board.flipCard("player1", 0, 1);
	 * ```
	 */
	public async flipCard(player: string, row: number, col: number): Promise<void> {
		this.checkRep();

		// 0. Coordinate validation
		if (row < 0 || row >= this.rows || col < 0 || col >= this.cols) {
			throw new Error(`Invalid coordinates (${row},${col})`);
		}

		let card = this.cards[row]?.[col];
		const key = `${row},${col}`;

		// 1. Initialize / get player state
		if (!this.playerState.has(player)) {
			this.playerState.set(player, {});
		}
		const state = this.playerState.get(player)!;

		// 2. Apply rules 3A / 3B only if the player is not in the middle of a pair
		if (!state.first && !state.second) {
			// 3A: remove the matched pair
			if (state.lastMatch) {
				for (const pos of state.lastMatch) {
					if (this.cards[pos.row]?.[pos.col] != null) {
						this.faceUp[pos.row]![pos.col] = false;
						this.control[pos.row]![pos.col] = null;
						this.cards[pos.row]![pos.col] = null;
						this.releaseControl(pos.row, pos.col);
					}
				}
				state.lastMatch = undefined;
				this.notifyWatchers(); // 🔔 notify card removal
			}

			// 3B: flip mismatched cards back down
			if (state.lastMismatch) {
				let flippedDown = false;
				for (const pos of state.lastMismatch) {
					const exists = this.cards[pos.row]?.[pos.col] != null;
					const noController = this.control[pos.row]?.[pos.col] === null;
					const isUp = this.faceUp[pos.row]?.[pos.col];
					if (exists && noController && isUp) {
						this.faceUp[pos.row]![pos.col] = false;
						flippedDown = true;
					}
				}
				state.lastMismatch = undefined;
				if (flippedDown) this.notifyWatchers(); // 🔔 notify flipping back down
			}
		}

		// 3. Rule 1-D (waiting) — only if the player doesn't have a card controlled
		if (!state.first && !state.second && this.faceUp[row]?.[col] && this.control[row]?.[col] && this.control[row]![col] !== player) {
			const deferred = new Deferred<void>();
			if (!this.waiting.has(key)) this.waiting.set(key, []);
			this.waiting.get(key)!.push(deferred);
			await deferred.promise;
			card = this.cards[row]?.[col];
		}

		// === FIRST card ===
		if (!state.first) {
			if (this.cards[row]?.[col] == null) throw new Error("No card at that position");

			// if it's still controlled by someone else -> error
			if (this.control[row]![col] && this.control[row]![col] !== player) {
				throw new Error("Card controlled by another player");
			}

			this.faceUp[row]![col] = true;
			this.control[row]![col] = player;
			state.first = { row, col, card: this.cards[row]![col]! as string };

			this.notifyWatchers(); // 🔔 notify flipping of the first card
			return;
		}

		// === SECOND card ===
		if (!state.second) {
			if (row === state.first.row && col === state.first.col) {
				// Ignore double click on the same card
				return;
			}

			// 2A: second position is empty -> lose the first one
			if (this.cards[row]?.[col] == null) {
				this.control[state.first.row]![state.first.col] = null;
				this.releaseControl(state.first.row, state.first.col);
				state.lastMismatch = [state.first];
				state.first = undefined;
				this.notifyWatchers(); // 🔔 notify loss of control
				throw new Error("No card at that position");
			}

			// 2B: second card is already controlled -> no wait, lose the first one
			if (this.control[row]?.[col] && this.control[row]![col] !== player) {
				this.control[state.first.row]![state.first.col] = null;
				this.releaseControl(state.first.row, state.first.col);
				state.lastMismatch = [state.first];
				state.first = undefined;
				this.notifyWatchers(); // 🔔 notify loss of control
				throw new Error("Card already controlled");
			}

			// 2C: flip the second card
			this.faceUp[row]![col] = true;
			this.control[row]![col] = player;
			state.second = { row, col, card: this.cards[row]![col]! as string };
			this.notifyWatchers(); // 🔔 notify flipping of the second card

			// 2D / 2E: compare
			if (state.first.card === state.second.card) {
				state.lastMatch = [state.first, state.second];
			} else {
				this.control[state.first.row]![state.first.col] = null;
				this.control[state.second.row]![state.second.col] = null;
				this.releaseControl(state.first.row, state.first.col);
				this.releaseControl(state.second.row, state.second.col);
				state.lastMismatch = [state.first, state.second];
			}

			state.first = undefined;
			state.second = undefined;

			this.notifyWatchers(); // 🔔 notify final comparison
			return;
		}

		// 3+ cards — error
		throw new Error("Player cannot flip a third card without completing a pair");
	}

	/**
	 * Returns a string representation of the board from a player's perspective.
	 *
	 * Output format: One card state per line
	 * - "none" - Card has been removed
	 * - "down" - Card is face-down
	 * - "my <card>" - Card is face-up and controlled by this player
	 * - "up <card>" - Card is face-up and controlled by another player
	 *
	 * @param player - The player ID to show the perspective for
	 * @returns A formatted string showing the board state
	 *
	 * @example
	 * ```typescript
	 * const view = board.toDisplayString("player1");
	 * console.log(view);
	 * // Output:
	 * // 2x2
	 * // my A
	 * // down
	 * // up B
	 * // none
	 * ```
	 */
	public toDisplayString(player: string): string {
		let output = `${this.rows}x${this.cols}\n`;
		for (let r = 0; r < this.rows; r++) {
			for (let c = 0; c < this.cols; c++) {
				const card = this.cards[r]![c];
				if (card === null) {
					output += "none\n";
				} else if (!this.faceUp[r]![c]!) {
					output += "down\n";
				} else if (this.control[r]![c] === player) {
					output += `my ${card}\n`;
				} else {
					output += `up ${card}\n`;
				}
			}
		}
		return output;
	}

	public toString(): string {
		let s = "";
		for (let r = 0; r < this.rows; r++) {
			for (let c = 0; c < this.cols; c++) {
				const card = this.cards[r]![c];
				const state = card === null ? "none" : this.faceUp[r]![c]! ? "up" : "down";
				s += `${card ?? "none"}(${state}) `;
			}
			s += "\n";
		}
		return s;
	}

	public isFaceUp(row: number, col: number): boolean {
		return !!this.faceUp[row]?.[col];
	}

	public controlledBy(row: number, col: number): string | null {
		return this.control[row]?.[col] ?? null;
	}

	/**
	 * Transforms all cards on the board using an async function.
	 *
	 * The transformation function is applied to every non-removed card asynchronously.
	 * This operation may interleave with other game actions and does not block flips.
	 * Removed cards (null) are skipped. Cards that are removed during transformation are not replaced.
	 *
	 * @param f - An async function that takes a card value and returns the transformed value
	 * @returns A Promise that resolves when all transformations are complete
	 *
	 * @example
	 * ```typescript
	 * // Convert all cards to lowercase
	 * await board.mapCards(async (card) => card.toLowerCase());
	 *
	 * // Add a suffix to each card
	 * await board.mapCards(async (card) => card + "!");
	 * ```
	 */
	public async mapCards(f: (card: string) => Promise<string>): Promise<void> {
		const tasks: Promise<void>[] = [];

		for (let r = 0; r < this.rows; r++) {
			for (let c = 0; c < this.cols; c++) {
				const card = this.cards[r]?.[c];
				if (card !== null && card !== undefined) {
					// Transform this card asynchronously
					const task = (async () => {
						const newCard = await f(card);
						// only replace if card still exists (wasn't removed)
						if (this.cards[r]?.[c] !== null) {
							this.cards[r]![c] = newCard;
						}
					})();
					tasks.push(task);
				}
			}
		}

		await Promise.all(tasks);
		this.notifyWatchers();
	}

	/**
	 * Notifies all watchers that the board has changed and clears the watcher list.
	 *
	 * Called internally when cards are flipped, removed, or transformed.
	 * Resolves all pending watch() promises.
	 *
	 * @private
	 */
	private notifyWatchers(): void {
		for (const watcher of this.watchers) {
			watcher.resolve();
		}
		this.watchers = []; // clear after notifying
	}

	/**
	 * Waits until the board changes (a card is flipped, removed, or transformed).
	 *
	 * This is useful for detecting visible board state changes. Control-only changes
	 * (e.g., a player gaining/losing control) do not trigger watchers.
	 *
	 * @returns A Promise that resolves when the board changes
	 *
	 * @example
	 * ```typescript
	 * const watcher = board.watch();
	 * // ... perform some async actions ...
	 * await watcher; // Wait for any board change
	 * ```
	 */
	public async watch(): Promise<void> {
		const deferred = new Deferred<void>();
		this.watchers.push(deferred);
		await deferred.promise;
	}
}
