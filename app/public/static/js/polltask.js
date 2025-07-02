// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";


async function getJSON(url, method) {
	const response = await fetch(new Request(url, {
			method: method || "get",
			credentials: "same-origin",
			headers: {
				"Accept": "application/json",
			},
		}));

	return await response.json();
}


function sleep(interval) {
	return new Promise(resolve => setTimeout(resolve, interval));
}


async function pollTask(poll_url, disableTimeout, onProgress) {
	let tries = 0;

	while (true) {
		tries++;
		if (!disableTimeout && tries > 30) {
			throw "timeout";
		} else {
			const interval = Math.min(tries * 100, 1000);
			console.log("Polling task in " + interval + "ms");
			await sleep(interval);
		}

		let res = undefined;
		try {
			res = await getJSON(poll_url);
		} catch (e) {
			console.error(e);
		}

		if (res && res.status) {
			onProgress?.(res);
		}

		if (res && res.status === "SUCCESS") {
			console.log("Got result")
			return res.result;
		} else if (res && (res.status === "FAILURE" || res.status === "REVOKED")) {
			throw res.error ?? "Unknown server error";
		}
	}
}


async function performTask(url) {
	const startResult = await getJSON(url, "post");
	console.log(startResult);

	if (typeof startResult.poll_url == "string") {
		return await pollTask(startResult.poll_url);
	} else {
		throw "Start task didn't return string!";
	}
}

window.addEventListener("load", () => {
	const taskId = document.querySelector("[data-task-id]")?.getAttribute("data-task-id");
	if (taskId) {
		const progress = document.getElementById("progress");

		function onProgress(res) {
			let status = res.status.toLowerCase();
			if (status === "progress") {
				progress.classList.remove("d-none");
				const bar = progress.children[0];

				const {current, total, running} = res.result;
				const perc = Math.min(Math.max(100 * current / total, 0), 100);
				bar.style.width = `${perc}%`;
				bar.setAttribute("aria-valuenow", current);
				bar.setAttribute("aria-valuemax", total);

				const packages = (running ?? []).map(x => `${x.author}/${x.name}`).join(", ");
				document.getElementById("status").textContent = `Status: in progress (${current} / ${total})\n\n${packages}`;
			} else {
				progress.classList.add("d-none");

				if (status === "pending") {
					status = "pending or unknown";
				}
				document.getElementById("status").textContent = `Status: ${status}`;
			}
		}

		pollTask(`/tasks/${taskId}/`, true, onProgress)
			.then(function() { location.reload() })
			.catch(function(e) {
				console.error(e);
				location.reload();
			});
	}
});
