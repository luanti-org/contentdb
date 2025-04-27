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


async function pollTask(poll_url, disableTimeout) {
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
			let status = res.status.toLowerCase();
			if (status === "pending") {
				status = "pending or unknown";
			}
			document.getElementById("status").textContent = `Status: ${status}`;
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
