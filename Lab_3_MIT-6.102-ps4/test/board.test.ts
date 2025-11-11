import { expect, use } from "chai";
import chaiAsPromised from "chai-as-promised";
import { Board } from "../src/board.js";

use(chaiAsPromised);

// mic helper pentru delay concurent
const delay = (ms: number) => new Promise((res) => setTimeout(res, ms));

describe("Board ADT concurrent game rules", function () {
	let board: Board;

	beforeEach(async function () {
		// 2x2 board simplu, ușor de testat
		board = new Board(2, 2, [
			["A", "A"],
			["B", "B"],
		]);
	});

	// ------------------ RULE 1: first card ------------------

	it("player can flip first face-down card and gain control", async function () {
		await board.flipCard("p1", 0, 0);
		const view = board.toDisplayString("p1");
		expect(view).to.include("my A");
	});

	it("another player waits if first card is controlled", async function () {
		const flip1 = board.flipCard("p1", 0, 0);
		const flip2 = board.flipCard("p2", 0, 0);

		// primul se termină normal
		await flip1;
		// al doilea trebuie să rămână pending până se eliberează
		const pending = Promise.race([flip2.then(() => "done"), delay(50).then(() => "timeout")]);

		expect(await pending).to.equal("timeout");
	});

	// ------------------ RULE 2: second card ------------------

	it("matching cards stay face up and controlled", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 1); // match A-A
		const view = board.toDisplayString("p1");
		expect(view).to.include("my A");
	});

	it("mismatched second card leaves both face up, then turns down next turn", async function () {
		await board.flipCard("p1", 0, 0); // A
		await board.flipCard("p1", 1, 0); // B -> mismatch

		let view = board.toDisplayString("p1");
		expect(view).to.include("up A");
		expect(view).to.include("up B");

		// la următoarea mișcare, 3B se aplică
		await board.flipCard("p1", 1, 1); // nou first card
		view = board.toDisplayString("p1");
		expect(view).to.include("down"); // ambele nepotrivite s-au întors
	});

	it("cannot flip a card already controlled by another player (blocks or waits)", async function () {
		await board.flipCard("p1", 0, 0);
		const p2Flip = board.flipCard("p2", 0, 0);
		// al doilea flip trebuie să aștepte, nu să arunce
		const state = await Promise.race([p2Flip.then(() => "resolved"), delay(30).then(() => "pending")]);
		expect(state).to.equal("pending");
	});

	// ------------------ RULE 3: removal / flip down ------------------

	it("matched pair is removed on next move", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 1); // match A-A
		await board.flipCard("p1", 1, 0); // next move triggers 3A removal

		const view = board.toDisplayString("p1");
		expect(view).to.include("none");
	});

	// ------------------ EDGE CASES ------------------

	it("invalid coordinates should reject", async function () {
		try {
			await board.flipCard("p1", 9, 0);
			throw new Error("Expected flipCard to reject for invalid coordinates");
		} catch (err: any) {
			expect(err).to.be.instanceOf(Error);
			expect(err.message).to.include("Invalid coordinates");
		}
	});
});
