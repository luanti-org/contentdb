// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

function startVideoEmbed(ele, url) {
	ele.querySelector(".video-preview").classList.add("d-none");

	const embedContainer = ele.querySelector(".video-content");
	embedContainer.classList.remove("d-none");
	embedContainer.innerHTML = `
		<iframe title="YouTube video player" frameborder="0"
				allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
				allowfullscreen>
		</iframe>`;

	const embedURL = new URL("https://www.youtube.com/");
	embedURL.pathname = "/embed/" + url.searchParams.get("v");
	embedURL.searchParams.set("autoplay", "1");

	const iframe = embedContainer.querySelector("iframe");
	iframe.setAttribute("src", embedURL);

	const event = new Event("videoStarted");
	ele.dispatchEvent(event);
}

function stopVideoEmbed(ele) {
	ele.querySelector(".video-preview").classList.remove("d-none");
	ele.querySelector(".video-content").classList.add("d-none");
	ele.querySelector(".video-content").innerHTML = "";
}

document.querySelectorAll(".video-embed").forEach(ele => {
	try {
		const href = ele.getAttribute("href");
		const url = new URL(href);

		if (url.host == "www.youtube.com") {
			ele.addEventListener("click", () => startVideoEmbed(ele, url));
			ele.addEventListener("stopVideo", () => stopVideoEmbed(ele));

			ele.setAttribute("data-src", href);
			ele.removeAttribute("href");

			ele.querySelector(".label").innerText = "YouTube";
		}
	} catch (e) {
		console.error(url);
		return;
	}
});
