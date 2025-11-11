import { Board } from "./board.js";

/**
 * Looks at the current state of the board.
 */
export async function look(board: Board, playerId: string): Promise<string> {
	return board.toDisplayString(playerId);
}

/**
 * Tries to flip a card on the board.
 */
export async function flip(board: Board, playerId: string, row: number, column: number): Promise<string> {
	await board.flipCard(playerId, row, column);
	return board.toDisplayString(playerId);
}

/**
 * Modifies the board by applying f(card) to every card.
 */
export async function map(board: Board, playerId: string, f: (card: string) => Promise<string>): Promise<string> {
	await board.mapCards(f);
	return board.toDisplayString(playerId);
}

/**
 * Watches the board for changes.
 * (implemented later in Problem 5)
 */
export async function watch(board: Board, playerId: string): Promise<string> {
	await board.watch();
	return board.toDisplayString(playerId);
}
