// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";


// Sets each widget's order field to its position in the list
function updateOrder() {
	const cards = document.querySelectorAll("#widget_list > .widget-card");
	cards.forEach((card, i) => {
		card.querySelector("input[name$='-order']").value = i.toString();
	});
}


function removeWidget(card) {
	const message = document.getElementById("confirm_remove").innerText.trim();
	if (!confirm(message)) {
		return;
	}

	card.querySelector("input[name$='-removed']").value = "1";
	card.classList.add("d-none");
}


function setupCard(card) {
	const removed = card.querySelector("input[name$='-removed']");

	// Reloading after a validation error keeps removed widgets in the form
	if (removed.value === "1") {
		card.classList.add("d-none");
	}

	card.querySelector(".remove-widget").addEventListener("click", () => removeWidget(card));
}


function getNextIndex() {
	let next = 0;
	document.querySelectorAll("#widget_list input[name$='-type']").forEach(input => {
		const match = input.name.match(/^widgets-(\d+)-type$/);
		if (match) {
			next = Math.max(next, parseInt(match[1]) + 1);
		}
	});
	return next;
}


function addWidget(type) {
	const template = document.getElementById(`widget_template_${type}`);
	const index = getNextIndex().toString();

	const temp = document.createElement("div");
	temp.innerHTML = template.innerHTML.replaceAll("__index__", index);

	const card = temp.querySelector(".widget-card");
	document.getElementById("widget_list").appendChild(card);
	setupCard(card);
	updateOrder();
	card.scrollIntoView();
}


window.addEventListener("load", () => {
	document.querySelectorAll("#widget_list > .widget-card").forEach(setupCard);

	document.querySelectorAll(".add-widget").forEach(button => {
		button.addEventListener("click", () => addWidget(button.dataset.type));
	});

	updateOrder();
	$(".sortable").sortable({
		update: updateOrder,
	});
});
