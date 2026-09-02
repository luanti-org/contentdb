// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

addEventListener("load", () => {
	const downloadCard = document.getElementById("download-card");
	downloadCard.classList.remove("d-none");

	const downloadNoJS = document.getElementById("download-nojs");
	downloadNoJS.classList.add("d-none");

	const luantiVersion = document.getElementById("luanti-version");
	luantiVersion.addEventListener("change", () => {
		setLuantiVersion(luantiVersion.selectedOptions[0]);
	});

	const luantiVersionId = localStorage.getItem("luanti-version");
	if (luantiVersionId && document.querySelector(`#luanti-version option[value='${luantiVersionId}']`)) {
		luantiVersion.value = luantiVersionId;
	}
	setLuantiVersion(luantiVersion.selectedOptions[0]);

	setupGameSelect().catch(console.error);
});

async function fetchGames() {
	const response = await fetch("/api/packages/?type=game");
	if (!response.ok) {
		throw new Error(`Failed to fetch games: ${response.status} ${response.statusText}`);
	}
	return await response.json();
}

async function setupGameSelect() {
	if (!document.getElementById("current-game")) {
		const gameId = document.getElementById("download-card").dataset.setGameId;
		if (gameId) {
			localStorage.setItem("current-game", gameId);
		}
		return;
	}

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

		const msg2 = alertIncompatible.querySelector("[data-game-incompatible-msg2]");
		msg2.textContent = msg2.dataset.gameIncompatibleMsg2.replace("@1", gameTitle);
	}
}

function setLuantiVersion(version) {
	if (!version) {
		return;
	}

	localStorage.setItem("luanti-version", version.value);

	const {
		packageName,
		releaseId,
		releaseName,
		releaseUrl,
		releaseSize,
		releaseCreatedAt,
		latest,
	} = version.dataset;

	const success = document.getElementById("download-success");
	const noRelease = document.getElementById("download-no-release");
	const newerLuanti = document.getElementById("download-newer-luanti");
	if (latest) {
		newerLuanti.classList.add("d-none");
	} else {
		newerLuanti.classList.remove("d-none");
	}

	if (releaseName) {
		success.classList.remove("d-none");
		noRelease.classList.add("d-none");

		const btn = document.querySelector("#download-card .btn-download");
		btn.setAttribute("href", releaseUrl);

		// See PackageRelease.get_download_filename()
		const filename = `${packageName}_${releaseId}.zip`;
		btn.setAttribute("download", filename);

		const size = document.getElementById("download-file-size");
		if (releaseSize > 1024*1024) {
			size.textContent = `[${(releaseSize / 1024 / 1024).toFixed(1)} MB]`;
		} else {
			size.textContent = `[${(releaseSize / 1024).toFixed(0)} KB]`;
		}

		const info = document.getElementById("download-release-info");
		info.textContent = info.dataset.releaseText
			.replace("@1", releaseName)
			.replace("@2", releaseCreatedAt);
	} else {
		success.classList.add("d-none");
		noRelease.classList.remove("d-none");
	}
}
