// @author rubenwardy
// @license magnet:?xt=urn:btih:1f739d935676111cfff4b4693e3816e664797050&dn=gpl-3.0.txt GPL-v3-or-Later

"use strict";

const labelColor = "#bbb";
const annotationColor = "#bbb";
const annotationLabelBgColor = "#444";
const gridColor = "#333";


const chartColors = [
	"#7eb26d",
	"#eab839",
	"#6ed0e0",
	"#e24d42",
	"#1f78c1",
	"#ba43a9",
];


const annotationNov5 = {
	type: "line",
	borderColor: annotationColor,
	borderWidth: 1,
	click: function({chart, element}) {
		document.location = "https://blog.rubenwardy.com/2022/12/08/contentdb-youtuber-finds-minetest/";
	},
	label: {
		backgroundColor: annotationLabelBgColor,
		content: "YouTube Video 🡕",
		display: true,
		position: "end",
		color: "#00bc8c",
		rotation: "auto",
		backgroundShadowColor: "rgba(0, 0, 0, 0.4)",
		shadowBlur: 3,
	},
	scaleID: "x",
	value: "2022-11-05",
};


function hexToRgb(hex) {
	var bigint = parseInt(hex, 16);
	var r = (bigint >> 16) & 255;
	var g = (bigint >> 8) & 255;
	var b = bigint & 255;

	return r + "," + g + "," + b;
}


function sum(list) {
	return list.reduce((acc, x) => acc + x, 0);
}


const chartColorsBg = chartColors.map(color => `rgba(${hexToRgb(color.slice(1))}, 0.2)`);

const SECONDS_IN_A_DAY = 1000 * 3600 * 24;


function format_message(id, values) {
	let format = document.getElementById(id).textContent;
	values.forEach((value, i) => {
		format = format.replace("$" + (i + 1), value);
	})
	return format;
}


function add_summary_card(title, icon, value, extra) {
	const ele = document.createElement("div");
	ele.innerHTML = `
		<div class="col-md-4">
			<div class="card h-100">
				<div class="card-body align-items-center text-center">
					<div class="mt-0 mb-3">
						<i class="fas fa-${icon} me-1"></i>
						<span class="summary-title"></span>
					</div>
					<div class="my-0 h4">
						<span class="summary-value"></span>
						<small class="text-muted ms-2 summary-extra"></small>
					</div>
				</div>
			</div>
		</div>`;

	ele.querySelector(".summary-title").textContent = title;
	ele.querySelector(".summary-value").textContent = value;
	ele.querySelector(".summary-extra").textContent = extra;

	document.getElementById("stats-summaries").appendChild(ele.children[0]);
}

async function load_data() {
	const root = document.getElementById("stats-root");
	const source = root.getAttribute("data-source");
	const is_range = root.getAttribute("data-is-range") == "true";
	const response = await fetch(source);
	const json = await response.json();

	document.getElementById("loading").style.display = "none";

	if (json == null) {
		document.getElementById("empty-view").style.display = "block";
		return;
	}

	const startDate = new Date(json.start);
	const endDate = new Date(json.end);
	const numberOfDays = Math.round((endDate.valueOf() - startDate.valueOf()) / SECONDS_IN_A_DAY) + 1;
	const dates = [...Array(numberOfDays)].map((_, i) => {
		const date = new Date(startDate.valueOf() + i*SECONDS_IN_A_DAY);
		return date.toISOString().split("T")[0];
	});

	if (!is_range) {
		if (json.platform_minetest.length >= 30) {
			const total30 = sum(json.platform_minetest.slice(-30)) + sum(json.platform_other.slice(-30));
			add_summary_card(format_message("downloads-30days", []), "download", total30,
					format_message("downloads-per-day", [ (total30 / 30).toFixed(0) ]));
		}

		const total7 = sum(json.platform_minetest.slice(-7)) + sum(json.platform_other.slice(-7));
		add_summary_card(format_message("downloads-7days", []), "download", total7,
				format_message("downloads-per-day", [ (total7 / 7).toFixed(0) ]));
	} else {
		const total = sum(json.platform_minetest) + sum(json.platform_other);
		const days = Math.max(json.platform_minetest.length, json.platform_other.length);
		const title = format_message("downloads-range", [ json.start, json.end ]);
		add_summary_card(title, "download", total,
				format_message("downloads-per-day", [ (total / days).toFixed(0) ]));
	}

	const jsonOther = json.platform_minetest.map((value, i) =>
			value + json.platform_other[i]
				- json.reason_new[i] - json.reason_dependency[i]
				- json.reason_update[i]);

	root.style.display = "block";

	function getData(list) {
		return list.map((value, i) => ({ x: dates[i], y: value }));
	}

	const annotations = {};
	if (new Date(json.start) < new Date("2022-11-05")) {
		annotations.annotationNov5 = annotationNov5;
	}

	if (json.package_downloads) {
		const packageRecentDownloads = Object.fromEntries(Object.entries(json.package_downloads)
			.map(([label, values]) => [label, sum(values.slice(-30))]));

		document.getElementById("downloads-by-package").classList.remove("d-none");
		const ctx = document.getElementById("chart-packages").getContext("2d");

		const data = {
			datasets: Object.entries(json.package_downloads)
				.sort((a, b) => packageRecentDownloads[a[0]] - packageRecentDownloads[b[0]])
				.map(([label, values]) => ({ label, data: getData(values) })),
		};
		setup_chart(ctx, data, annotations);
	}

	{
		const ctx = document.getElementById("chart-platform").getContext("2d");
		const data = {
			datasets: [
				{ label: "Web / other", data: getData(json.platform_other) },
				{ label: "Luanti", data: getData(json.platform_minetest) },
			],
		};
		setup_chart(ctx, data, annotations);
	}

	{
		const ctx = document.getElementById("chart-reason").getContext("2d");
		const data = {
			datasets: [
				{ label: "Other / Unknown", data: getData(jsonOther) },
				{ label: "Update", data: getData(json.reason_update) },
				{ label: "Dependency", data: getData(json.reason_dependency) },
				{ label: "New Install", data: getData(json.reason_new) },
			],
		};
		setup_chart(ctx, data, annotations);
	}

	{
		const ctx = document.getElementById("chart-reason-pie").getContext("2d");
		const data = {
			labels: [
				"New Install",
				"Dependency",
				"Update",
				"Other / Unknown",
			],
			datasets: [{
				label: "My First Dataset",
				data: [
					sum(json.reason_new),
					sum(json.reason_dependency),
					sum(json.reason_update),
					sum(jsonOther),
				],
				backgroundColor: chartColors,
				hoverOffset: 4,
				borderWidth: 0,
			}]
		};
		const config = {
			type: "doughnut",
			data: data,
			options: {
				responsive: true,
				plugins: {
					legend: {
						labels: {
							color: labelColor,
						},
					},
				},
			}
		};
		new Chart(ctx, config);
	}

	{
		const ctx = document.getElementById("chart-views").getContext("2d");
		const data = {
			datasets: [
				{ label: "Luanti", data: getData(json.views_minetest) },
			],
		};
		setup_chart(ctx, data, annotations);
	}
}


function setup_chart(ctx, data, annotations) {
	data.datasets = data.datasets.map((set, i) => {
		const colorIdx = (data.datasets.length - i - 1) % chartColors.length;
		return {
			fill: true,
			backgroundColor: chartColorsBg[colorIdx],
			borderColor: chartColors[colorIdx],
			pointBackgroundColor: chartColors[colorIdx],
			...set,
		};
	});

	const config = {
		type: "line",
		data: data,
		options: {
			responsive: true,
			plugins: {
				tooltip: {
					mode: "index"
				},

				legend: {
					reverse: true,
					labels: {
						color: labelColor,
					}
				},

				annotation: {
					annotations,
				},
			},
			interaction: {
				mode: "nearest",
				axis: "x",
				intersect: false
			},
			scales: {
				x: {
					type: "time",
					time: {
						// min: start,
						// max: end,
						unit: "day",
					},
					ticks: {
						color: labelColor,
					},
					grid: {
						color: gridColor,
					}
				},
				y: {
					stacked: true,
					min: 0,
					precision: 0,
					ticks: {
						color: labelColor,
					},
					grid: {
						color: gridColor,
					}
				},
			}
		}
	};

	new Chart(ctx, config);
}


window.addEventListener("load", load_data);
