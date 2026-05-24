// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

addEventListener("load", () => {
	const width = window.innerWidth;
	const tiles = document.querySelectorAll(".packagetile");
	tiles.forEach(tile => {
		const rect = tile.getBoundingClientRect();
		const centerX = rect.x + rect.width / 2;
		if (centerX > width / 2) {
			tile.classList.add("open-left")
		}
	});
});
