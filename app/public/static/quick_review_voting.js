// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

function getVoteCount(button) {
	const badge = button.querySelector(".badge");
	return badge ? parseInt(badge.textContent) : 0;
}

function setVoteCount(button, count) {
	let badge = button.querySelector(".badge");
	if (count == 0) {
		if (badge) {
			badge.remove();
		}
		return;
	}
	if (!badge) {
		badge = document.createElement("span")
		badge.classList.add("badge");
		badge.classList.add("bg-light");
		badge.classList.add("text-dark");
		badge.classList.add("ms-1");
		button.appendChild(badge);
	}

	badge.textContent = count.toString();
}


async function submitForm(form, is_helpful) {
	const data = new URLSearchParams();
	for (const pair of new FormData(form)) {
		data.append(pair[0], pair[1]);
	}
	data.set("is_positive", is_helpful ? "yes" : "no");

	const res = await fetch(form.getAttribute("action"), {
		method: "post",
		body: data,
		headers: {
			"Content-Type": "application/x-www-form-urlencoded",
		},
	});

	if (!res.ok) {
		console.error(await res.text());
	}
}


window.addEventListener("load", () => {
	document.querySelectorAll(".review-helpful-vote").forEach((helpful_form) => {
		const yes = helpful_form.querySelector("button[name='is_positive'][value='yes']");
		const no = helpful_form.querySelector("button[name='is_positive'][value='no']");

		function setVote(is_helpful) {
			const selected = is_helpful ? yes : no;
			const not_selected = is_helpful ? no : yes;

			if (not_selected.classList.contains("btn-primary")) {
				setVoteCount(not_selected, Math.max(getVoteCount(not_selected) - 1, 0));
			}
			if (selected.classList.contains("btn-secondary")) {
				setVoteCount(selected, getVoteCount(selected) + 1);
			}

			selected.classList.add("btn-primary");
			selected.classList.remove("btn-secondary");
			not_selected.classList.add("btn-secondary");
			not_selected.classList.remove("btn-primary");

			submitForm(helpful_form, is_helpful).catch(console.error);
		}

		yes.addEventListener("click", (e) => {
			setVote(true);
			e.preventDefault();
		});

		no.addEventListener("click", (e) => {
			setVote(false)
			e.preventDefault();
		});
	});
});
