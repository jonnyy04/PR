import { expect, use } from "chai";
import chaiAsPromised from "chai-as-promised";
import { Board } from "../src/board.js";

use(chaiAsPromised);

// short delay helper
const delay = (ms: number) => new Promise((res) => setTimeout(res, ms));

describe("Board ADT — full 20-test suite", function () {
	let board: Board;

	beforeEach(() => {
		board = new Board(2, 2, [
			["A", "A"],
			["B", "B"],
		]);
	});

	// =========================================================
	// 1. FIRST-CARD RULES (5 tests)
	// =========================================================

	it("1. player can flip a face-down first card", async function () {
		await board.flipCard("p1", 0, 0);
		const view = board.toDisplayString("p1");
		expect(view).to.include("my A");
	});

	it("2. another player waits if first card is controlled", async function () {
		const f1 = board.flipCard("p1", 0, 0);
		const f2 = board.flipCard("p2", 0, 0);
		await f1;

		const r = await Promise.race([f2.then(() => "done"), delay(40).then(() => "pending")]);
		expect(r).to.equal("pending");
	});

	it("3. first-card flip rejects if no card exists", async function () {
		board.getCards()![0]![0] = null;
		await expect(board.flipCard("p1", 0, 0)).to.be.rejectedWith("No card at that position");
	});

	it("4. flipping already-face-up but uncontested card gives control", async function () {
		board.getFaceUp()![0]![0] = true;
		await board.flipCard("p1", 0, 0);
		expect(board.controlledBy(0, 0)).to.equal("p1");
	});

	it("5. invalid coordinates reject", async function () {
		await expect(board.flipCard("p1", 99, 99)).to.be.rejectedWith("Invalid coordinates");
	});

	// =========================================================
	// 2. SECOND-CARD RULES (MATCH/MISMATCH, 7 tests)
	// =========================================================

	it("6. matching second card keeps both face up", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 1);

		const view = board.toDisplayString("p1");
		expect(view).to.include("my A");
	});

	it("7. mismatched second card leaves both face up", async function () {
		await board.flipCard("p1", 0, 0); // A
		await board.flipCard("p1", 1, 0); // B mismatch

		const view = board.toDisplayString("p1");
		expect(view).to.include("up A");
		expect(view).to.include("up B");
	});

	it("8. mismatch flips down on next first-card attempt", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 1, 0); // mismatch

		await board.flipCard("p1", 1, 1); // trigger 3B

		const view = board.toDisplayString("p1");
		expect(view).to.include("down");
	});

	it("9. second-card flip rejects if card removed", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 1); // match
		await board.flipCard("p1", 1, 0); // remove pair

		// now A's are gone
		await expect(board.flipCard("p1", 0, 0)).to.be.rejectedWith("No card at that position");
	});

	it("10. second card controlled by another player rejects immediately (no waiting)", async function () {
		await board.flipCard("p1", 0, 0); // prima carte p1
		await board.flipCard("p2", 1, 0); // prima carte p2 – acum (1,0) e controlată de p2
		await expect(board.flipCard("p1", 1, 0)).to.be.rejectedWith("Card already controlled");
	});

	it("11. second-card empty => reject + relinquish first", async function () {
		await board.flipCard("p1", 0, 0);
		board.getCards()![1]![1] = null;
		await expect(board.flipCard("p1", 1, 1)).to.be.rejectedWith("No card at that position");
		expect(board.controlledBy(0, 0)).to.equal(null);
	});

	it("12. double-clicking same card as second card is ignored", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 0); // should do nothing
		expect(board.controlledBy(0, 0)).to.equal("p1");
	});

	// =========================================================
	// 3. REMOVAL (2 tests)
	// =========================================================

	it("13. matched pair removed on next first-card move", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 1); // match
		await board.flipCard("p1", 1, 0); // remove

		const view = board.toDisplayString("p1");
		expect(view).to.include("none");
	});

	it("14. removal frees waiting players (rejects when card no longer exists)", async function () {
		await board.flipCard("p1", 0, 0);
		const wait = board.flipCard("p2", 0, 0); // p2 waits

		await board.flipCard("p1", 0, 1); // match A-A
		await board.flipCard("p1", 1, 0); // triggers 3A removal → wakes p2

		await expect(wait).to.be.rejectedWith("No card at that position");
	});

	// =========================================================
	// 4. mapCards() (3 tests)
	// =========================================================

	it("15. mapCards transforms all existing cards", async function () {
		await board.mapCards(async (c) => c.toLowerCase());
		const s = board.toString();
		expect(s).to.include("a");
	});

	it("16. mapCards does not modify removed cards", async function () {
		await board.flipCard("p1", 0, 0);
		await board.flipCard("p1", 0, 1); // match
		await board.flipCard("p1", 1, 0); // remove

		await board.mapCards(async () => "Z");
		const view = board.toDisplayString("p1");
		expect(view).to.include("none");
	});

	it("17. mapCards interleaves with flips (no blocking)", async function () {
		const flip = board.flipCard("p1", 0, 0);
		const mapping = board.mapCards(async (c) => c + "!");
		await flip;
		await mapping;

		const s = board.toString();
		expect(s).to.include("A!");
	});

	// =========================================================
	// 5. watch() (3 tests)
	// =========================================================

	it("18. watch resolves when a visible change happens", async function () {
		const w = board.watch();
		await delay(5);
		await board.flipCard("p1", 0, 0);
		await expect(w).to.be.fulfilled;
	});

	it("19. watch does not resolve for control-only changes", async function () {
		await board.flipCard("p1", 0, 0);

		const w = board.watch();
		// no visible card change — just messing with control
		board.getControl()![0]![0] = null;

		const r = await Promise.race([w.then(() => "resolved"), delay(40).then(() => "timeout")]);
		expect(r).to.equal("timeout");
	});

	it("20. mapCards triggers watch() resolution because card string changes", async function () {
		const w = board.watch();

		await delay(10);
		await board.mapCards(async (c) => c + "x");

		await expect(w).to.be.fulfilled;
	});
});
