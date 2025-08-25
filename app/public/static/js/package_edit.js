// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

function hide(sel) {
	document.querySelectorAll(sel).forEach(x => x.classList.add("d-none"));
}

function show(sel) {
	document.querySelectorAll(sel).forEach(x => x.classList.remove("d-none"));
}


window.addEventListener("load", () => {
	const typeEle = document.getElementById("type");
	typeEle.addEventListener("change", () => {
		show(".not_mod, .not_game, .not_txp");
		hide(".not_" + typeEle.value.toLowerCase());
	})
	show(".not_mod, .not_game, .not_txp");
	hide(".not_" + typeEle.value.toLowerCase());

	const forumsField = document.getElementById("forums");
	forumsField.addEventListener("paste", function(e) {
		try {
			const pasteData = e.clipboardData.getData('text');
			const url = new URL(pasteData);
			if (url.hostname === "forum.luanti.org") {
				forumsField.value = url.searchParams.get("t");
				e.preventDefault();
			}
		} catch (e) {
			console.log("Not a URL");
		}
	});

	const openForums = document.getElementById("forums-button");
	openForums.addEventListener("click", () => {
		window.open("https://forum.luanti.org/viewtopic.php?t=" + forumsField.value, "_blank");
	});

	function setupHints(id, hints) {
		function onChange(val) {
			val = val.toLowerCase();
			Object.entries(hints).forEach(([key, func]) => {
				if (func(val)) {
					document.getElementById(key).classList.remove("d-none");
				} else {
					document.getElementById(key).classList.add("d-none");
				}
			});
		}

		const field = document.getElementById(id);
		if (field.easy_mde) {
			field.easy_mde.codemirror.on("change", () => {
				const value = field.easy_mde.value();
				onChange(value);
			});
		} else {
			field.addEventListener("change", () => onChange(field.value));
			field.addEventListener("paste", () => onChange(field.value));
			field.addEventListener("keyup", () => onChange(field.value));
			field.addEventListener("input", () => onChange(field.value));
		}
		onChange(field.value);
	}

	setupHints("short_desc", {
		"short_desc_mods": (val) => val.indexOf("luanti") >= 0 || val.indexOf("minetest") >= 0 ||
				val.indexOf("mod") >= 0 || val.indexOf("modpack") >= 0 ||
				val.indexOf("mod pack") >= 0,
	});

	setupHints("desc", {
		"desc_page_link": (val) => {
			let packageUrl = window.location.href.replace("/edit/", "");
			if (packageUrl.indexOf("/packages/new/") >= 0) {
				const author = document.querySelector("form[data-author]").getAttribute("data-author");
				const name = document.getElementById("name").value;
				packageUrl = `/packages/${author}/${name}/`;
			}
			return val.indexOf(packageUrl.toLowerCase()) >= 0;
		},
		"desc_page_topic": (val) => {
			const topicId = document.getElementById("forums").value;
			const r = new RegExp(`forum\\.minetest\\.net\\/viewtopic\\.php\\?[a-z0-9=&]*t=${topicId}`);
			const r2 = new RegExp(`forum\\.luanti\\.org\\/viewtopic\\.php\\?[a-z0-9=&]*t=${topicId}`);
			return topicId && (r.test(val) || r2.test(val));
		},
		"desc_page_repo": (val) => {
			const repoUrl = document.getElementById("repo").value.replace(".git", "");
			return repoUrl && val.indexOf(repoUrl.toLowerCase()) >= 0;
		},
	});
})
