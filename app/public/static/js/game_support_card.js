// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

addEventListener("load", () => {
	const gameSupportCard = document.getElementById("game-support-card");
	if (gameSupportCard) {
		gameSupportCard.classList.remove("d-none");
		setupGameSelect().catch(console.error);
	}
});

async function fetchGames() {
	const response = await fetch("/api/packages/?type=game");
	if (!response.ok) {
		throw new Error(`Failed to fetch games: ${response.status} ${response.statusText}`);
	}
	return await response.json();
}

async function setupGameSelect() {
	const games = await fetchGames();

	function getTitleFromGameId(gameId) {
		const game = games.find(row => `${row.author}/${row.name}` === gameId);
		return game ? game.title : gameId;
	}

	$("#current-game").autocomplete({
		source: games.map(row => (`${row.author}/${row.name}`)),
	});

	$("#current-game").on("autocompleteselect", (event, ui) => {
		const gameId = ui.item.value;
		localStorage.setItem("current-game", gameId);
		setGame(gameId, getTitleFromGameId(gameId));
	});

	const currentGame = localStorage.getItem("current-game");
	if (currentGame) {
		document.getElementById("current-game").value = currentGame;
		setGame(currentGame, getTitleFromGameId(currentGame));
	}

	document.getElementById("clear-current-game").addEventListener("click", () => {
		localStorage.removeItem("current-game");
		const currentGameField = document.getElementById("current-game")
		currentGameField.value = "";
		currentGameField.focus();
		setGame(null, null);
	});
}

function setGame(gameId, gameTitle) {
	const alertInitial = document.getElementById("alert-game-initial");
	const alertSuccess = document.getElementById("alert-game-success");
	const alertIncompatible = document.getElementById("alert-game-incompatible");

	if (!gameId) {
		alertInitial.classList.remove("d-none");
		alertSuccess.classList.add("d-none");
		alertIncompatible.classList.add("d-none");
		return;
	}

	alertInitial.classList.add("d-none");
	const isSupported = !!document.querySelector(`[data-supported-game-id="${gameId}"]`);
	const isUnsupported = !!document.querySelector(`[data-unsupported-game-id="${gameId}"]`);
	const noSpecificGame = !!document.querySelector("[data-game-no-specific-game]");
	console.log("Setting game:", gameId, isSupported, isUnsupported, noSpecificGame);

	 if ((isSupported || noSpecificGame) && !isUnsupported) {
		alertSuccess.classList.remove("d-none");
		alertIncompatible.classList.add("d-none");

		const msg = alertSuccess.querySelector("[data-game-success-msg]");
		msg.textContent = msg.dataset.gameSuccessMsg.replace("@1", gameTitle);
	} else {
		alertSuccess.classList.add("d-none");
		alertIncompatible.classList.remove("d-none");

		const msg = alertIncompatible.querySelector("[data-game-incompatible-msg]");
		msg.textContent = msg.dataset.gameIncompatibleMsg.replace("@1", gameTitle);
	}
}
