// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

// Editor for a WTForms FieldList of FormFields, as used by the dashboard and slide editors.
//
// * The list: <div class="sortable form-list" id="..." data-prefix="widgets" data-confirm-remove="...">
// * Each item: <article class="form-list-item"> containing hidden `<prefix>-N-order` and `<prefix>-N-removed`
//   inputs, and a `.form-list-remove` button.
// * Add buttons: <button class="form-list-add" data-list="list id" data-template="template id">. The template's
//   content is an item, with `__index__` in place of N.


// Sets each item's order field to its position in the list
function updateOrder(list) {
	list.querySelectorAll(":scope > .form-list-item").forEach((item, i) => {
		item.querySelector("input[name$='-order']").value = i.toString();
	});
}


function removeItem(list, item) {
	const message = list.dataset.confirmRemove;
	if (message && !confirm(message)) {
		return;
	}

	item.querySelector("input[name$='-removed']").value = "1";
	item.classList.add("d-none");
}


function setupItem(list, item) {
	// Reloading after a validation error keeps removed items in the form
	if (item.querySelector("input[name$='-removed']").value === "1") {
		item.classList.add("d-none");
	}

	item.querySelector(".form-list-remove").addEventListener("click", () => removeItem(list, item));
}


function getNextIndex(list) {
	const pattern = new RegExp(`^${list.dataset.prefix}-(\\d+)-removed$`);
	let next = 0;
	list.querySelectorAll("input[name$='-removed']").forEach(input => {
		const match = input.name.match(pattern);
		if (match) {
			next = Math.max(next, parseInt(match[1]) + 1);
		}
	});
	return next;
}


function addItem(list, template) {
	const temp = document.createElement("div");
	temp.innerHTML = template.innerHTML.replaceAll("__index__", getNextIndex(list).toString());

	const item = temp.querySelector(".form-list-item");
	list.appendChild(item);
	setupItem(list, item);
	updateOrder(list);
	item.scrollIntoView();
}


window.addEventListener("load", () => {
	document.querySelectorAll(".form-list").forEach(list => {
		list.querySelectorAll(":scope > .form-list-item").forEach(item => setupItem(list, item));
		updateOrder(list);
		$(list).sortable({
			update: () => updateOrder(list),
		});
	});

	document.querySelectorAll(".form-list-add").forEach(button => {
		button.addEventListener("click", () => {
			const list = document.getElementById(button.dataset.list);
			const template = document.getElementById(button.dataset.template);
			addItem(list, template);
		});
	});
});
