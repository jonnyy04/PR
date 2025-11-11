/* Copyright (c) 2021-25 MIT 6.102/6.031 course staff, all rights
 * reserved. Redistribution of original or derived work requires
 * permission of course staff.
 */

import assert from "node:assert";
import { Board } from "./board.js";

/**
 * Example simulation of concurrent players flipping cards.
 *
 * Goal: ensure the board runs without deadlocks or crashes.
 *
 * Run with:
 *    npm run simulation
 */
async function simulationMain(): Promise<void> {
	const filename = "boards/perfect.txt";
	const board: Board = await Board.parseFromFile(filename);

	const rows = board.getRows();
	const cols = board.getCols();

	const players = 20; // many players to stress concurrency
	const triesPerPlayer = 10;
	const maxDelayMs = 10;

	type Stats = {
		successfulMoves: number;
		failedMoves: number;
		matches: number;
		errors: number;
	};

	const playerStats = new Map<string, Stats>();

	console.log(`Starting simulation with ${players} players on ${rows}x${cols} board`);

	const playerPromises: Array<Promise<void>> = [];
	for (let p = 0; p < players; ++p) {
		playerPromises.push(simulatePlayer(`p${p + 1}`));
	}

	await Promise.all(playerPromises);
	console.log("✅ Simulation complete — no crashes or deadlocks detected");

	/** Simulate a single player performing random moves */
	async function simulatePlayer(playerId: string): Promise<void> {
		console.log(`🎮 ${playerId} joined the game`);

		playerStats.set(playerId, {
			successfulMoves: 0,
			failedMoves: 0,
			matches: 0,
			errors: 0,
		});

		for (let t = 0; t < triesPerPlayer; t++) {
			let r1 = -1,
				c1 = -1;
			let r2 = -1,
				c2 = -1;

			try {
				let attempts = 0;
				const maxAttempts = 3;

				// === Prima carte ===
				while (attempts < maxAttempts) {
					try {
						await timeout(Math.random() * maxDelayMs);
						r1 = randomInt(rows);
						c1 = randomInt(cols);

						// Dacă e ocupată de altcineva -> va intra în așteptare în flipCard (1-D),
						// noi doar logăm frumos înainte
						const controller = board.controlledBy(r1, c1);
						const isUp = board.isFaceUp(r1, c1);

						if (isUp && controller !== null && controller !== playerId) {
							console.log(`🕒 ${playerId} wants first card at (${r1},${c1}) but it's busy (controlled by ${controller}), will wait...`);
						} else {
							console.log(`👆 ${playerId} tries first flip at (${r1},${c1})`);
						}

						await board.flipCard(playerId, r1, c1);
						console.log(`✅ ${playerId} turn ${t}: first flip at (${r1},${c1})`);
						break;
					} catch (err) {
						attempts++;
						if (attempts === maxAttempts) throw err;
						await timeout(10);
					}
				}

				// === A doua carte ===
				await timeout(Math.random() * maxDelayMs);
				attempts = 0;

				while (attempts < maxAttempts) {
					try {
						do {
							r2 = randomInt(rows);
							c2 = randomInt(cols);
						} while (r2 === r1 && c2 === c1);

						await board.flipCard(playerId, r2, c2);
						console.log(`📍 ${playerId} turn ${t}: second flip at (${r2},${c2})`);
						break;
					} catch (err) {
						attempts++;
						if (attempts === maxAttempts) throw err;
						await timeout(10);
					}
				}

				const stats = playerStats.get(playerId)!;
				stats.successfulMoves++;

				// Snapshot după fiecare 5 mutări ale acestui jucător
				if ((t + 1) % 5 === 0) {
					console.log(`\n🔍 Board snapshot after ${playerId} turn ${t + 1}:`);
					console.log(board.toString());
					console.log("------------------------------------\n");
				}
			} catch (err) {
				const stats = playerStats.get(playerId)!;
				stats.failedMoves++;

				const message = (err as Error).message;
				if (message.includes("No card at that position")) {
					console.log(`💫 ${playerId}: Tried empty position (${r1},${c1})`);
				} else if (message.includes("Card controlled")) {
					console.log(`🔒 ${playerId}: Card already in use`);
				} else {
					console.error(`❌ ${playerId} error at turn ${t}:`, message);
					stats.errors++;
				}
			}
		}
	}
}

/** Random integer [0, max) */
function randomInt(max: number): number {
	return Math.floor(Math.random() * max);
}

/** Sleep helper */
async function timeout(ms: number): Promise<void> {
	const { promise, resolve } = Promise.withResolvers<void>();
	setTimeout(resolve, ms);
	return promise;
}

void simulationMain();
