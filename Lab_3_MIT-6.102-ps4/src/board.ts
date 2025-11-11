/* Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights reserved.
 * Redistribution of original or derived work requires permission of course staff.
 */

import assert from "node:assert";
import fs from "node:fs";

class Deferred<T> {
	promise: Promise<T>;
	resolve!: (value: T) => void;

	constructor() {
		this.promise = new Promise<T>((res) => {
			this.resolve = res;
		});
	}
}

/**
 * Mutable class representing the Memory Scramble game board.
 */
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

	// jucători care așteaptă să preia controlul unei cărți
	private waiting: Map<string, Deferred<void>[]> = new Map();
	// Observatori pentru schimbările de pe tablă
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
	 * Verifică invarianta internă a tablei.
	 * Dacă apare o eroare aici, înseamnă că logica jocului a lăsat starea inconsistentă.
	 */
	private checkRep(): void {
		assert(this.rows > 0 && this.cols > 0, `Eroare: tabla trebuie să aibă dimensiuni pozitive, dar are ${this.rows}x${this.cols}`);
		assert(this.cards.length === this.rows, `Eroare: numărul de rânduri din cards (${this.cards.length}) nu corespunde cu rows (${this.rows})`);

		for (let i = 0; i < this.cards.length; i++) {
			const row = this.cards[i];
			assert(row !== undefined, `Eroare: rândul ${i} este undefined`);
			assert(row.length === this.cols, `Eroare: rândul ${i} are ${row.length} coloane, dar ar trebui ${this.cols}`);
		}

		for (let r = 0; r < this.rows; r++) {
			for (let c = 0; c < this.cols; c++) {
				const card = this.cards[r]?.[c];
				const faceUp = this.faceUp[r]?.[c];
				const controller = this.control[r]?.[c];

				if (card === null && faceUp) {
					throw new Error(`Eroare: cartea (${r},${c}) a fost eliminată (null), dar faceUp[r][c] este TRUE.`);
				}
				if (card === null && controller !== null) {
					throw new Error(`Eroare: cartea (${r},${c}) este null, dar control[r][c] = '${controller}'.`);
				}
				if (card === undefined) {
					throw new Error(`Eroare: cartea (${r},${c}) este undefined (poate lipsă în vectorul cards).`);
				}
				if (card !== null) {
					if (faceUp === undefined) throw new Error(`Eroare: faceUp[${r}][${c}] este undefined pentru o carte existentă.`);
					if (controller === undefined) throw new Error(`Eroare: control[${r}][${c}] este undefined pentru o carte existentă.`);
				}
			}
		}
	}

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
	 * Enhanced flip logic (matching version):
	 * - Player flips a card face-up
	 * - If two of the same value are face-up → remove them
	 * - If two different cards are face-up → flip both back down
	 */
	// Helper nou: eliberează controlul și notifică eventualii așteptători

	public async flipCard(player: string, row: number, col: number): Promise<void> {
		this.checkRep();

		// 0. Validare coordonate
		if (row < 0 || row >= this.rows || col < 0 || col >= this.cols) {
			throw new Error(`Invalid coordinates (${row},${col})`);
		}

		let card = this.cards[row]?.[col];
		const key = `${row},${col}`;

		// 1. Inițializează / obține starea jucătorului
		if (!this.playerState.has(player)) {
			this.playerState.set(player, {});
		}
		const state = this.playerState.get(player)!;

		// 2. Aplică regulile 3A / 3B doar dacă jucătorul nu e în mijlocul unei perechi
		if (!state.first && !state.second) {
			// 3A: elimină perechea potrivită
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
				this.notifyWatchers(); // 🔔 notificăm eliminarea cărților
			}

			// 3B: întoarce în jos cărțile nepotrivite
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
				if (flippedDown) this.notifyWatchers(); // 🔔 notificăm întoarcerea în jos
			}
		}

		// 3. Regula 1-D (așteptare) — doar dacă jucătorul nu are nicio carte controlată
		if (!state.first && !state.second && this.faceUp[row]?.[col] && this.control[row]?.[col] && this.control[row]![col] !== player) {
			const deferred = new Deferred<void>();
			if (!this.waiting.has(key)) this.waiting.set(key, []);
			this.waiting.get(key)!.push(deferred);
			await deferred.promise;
			card = this.cards[row]?.[col];
		}

		// === PRIMA carte ===
		if (!state.first) {
			if (this.cards[row]?.[col] == null) throw new Error("No card at that position");

			// dacă încă e controlată de altcineva -> eroare
			if (this.control[row]![col] && this.control[row]![col] !== player) {
				throw new Error("Card controlled by another player");
			}

			this.faceUp[row]![col] = true;
			this.control[row]![col] = player;
			state.first = { row, col, card: this.cards[row]![col]! as string };

			this.notifyWatchers(); // 🔔 notificăm întoarcerea primei cărți
			return;
		}

		// === A DOUA carte ===
		if (!state.second) {
			if (row === state.first.row && col === state.first.col) {
				// Ignoră dublul click pe aceeași carte
				return;
			}

			// 2A: a doua poziție goală -> pierzi prima
			if (this.cards[row]?.[col] == null) {
				this.control[state.first.row]![state.first.col] = null;
				this.releaseControl(state.first.row, state.first.col);
				state.lastMismatch = [state.first];
				state.first = undefined;
				this.notifyWatchers(); // 🔔 notificăm pierderea controlului
				throw new Error("No card at that position");
			}

			// 2B: a doua carte e deja controlată -> nu așteaptă, pierzi prima
			if (this.control[row]?.[col] && this.control[row]![col] !== player) {
				this.control[state.first.row]![state.first.col] = null;
				this.releaseControl(state.first.row, state.first.col);
				state.lastMismatch = [state.first];
				state.first = undefined;
				this.notifyWatchers(); // 🔔 notificăm pierderea controlului
				throw new Error("Card already controlled");
			}

			// 2C: întoarce a doua carte
			this.faceUp[row]![col] = true;
			this.control[row]![col] = player;
			state.second = { row, col, card: this.cards[row]![col]! as string };
			this.notifyWatchers(); // 🔔 notificăm întoarcerea a doua carte

			// 2D / 2E: compară
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

			this.notifyWatchers(); // 🔔 notificăm comparația finală
			return;
		}

		// 3+ cărți — eroare
		throw new Error("Player cannot flip a third card without completing a pair");
	}

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
	 * Apply a transformation function f(card) asynchronously to every card on the board.
	 * This does not change faceUp or control state, and may interleave with other operations.
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
	}

	/**
	 * Notify all watchers that the board has changed.
	 */
	private notifyWatchers(): void {
		for (const watcher of this.watchers) {
			watcher.resolve();
		}
		this.watchers = []; // clear after notifying
	}

	/**
	 * Waits until the board changes (a card flips, is removed, or replaced).
	 */
	public async watch(): Promise<void> {
		const deferred = new Deferred<void>();
		this.watchers.push(deferred);
		await deferred.promise;
	}
}
