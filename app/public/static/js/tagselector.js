/*!
 * Tag Selector plugin for jQuery: Facilitates selecting multiple tags by extending jQuery UI Autocomplete.
 * License: MIT
 * https://petprojects.googlecode.com/svn/trunk/MIT-LICENSE.txt
 */

"use strict";

(function($) {
	// Tag titles and descriptions are written by editors, so they're escaped before going into HTML
	function escape_html(text) {
		return $("<div>").text(text).html();
	}

	function make_bold(text) {
		const idx = text.indexOf(":");
		if (idx > 0) {
			return `<b>${escape_html(text.substring(0, idx))}</b>` +
				`<span class="text-muted">: ${escape_html(text.substring(idx + 1))}</span>`;
		} else {
			return `<b>${escape_html(text)}</b>`;
		}
	}

	function hide_error(input) {
		const err = input.parent().parent().find(".invalid-remaining");
		err.hide();
	}

	function show_error(input, msg) {
		const err = input.parent().parent().find(".invalid-remaining");
		err.text(msg);
		err.show();
	}

	$.fn.selectSelector = function(source, select) {
		return this.each(function() {
			const selector = $(this),
				input = $('input[type=text]', this);

			const lookup = {};
			for (let i = 0; i < source.length; i++) {
				lookup[source[i].id] = source[i];
			}

			selector.click(() => input.focus())
				.delegate('.badge a', 'click', function() {
					const id = $(this).parent().data("id");
					select.find("option[value=" + id + "]").attr("selected", false)
					recreate();
				});

			function addTag(item) {
				const id = item.id;

				let text = item.text;
				const idx = text.indexOf(':');
				if (idx > 0) {
					text = text.substr(0, idx);
				}

				$('<span class="badge rounded-pill bg-primary"/>')
					.text(text + ' ')
					.data("id", id)
					.append('<a>x</a>')
					.insertBefore(input);
				input.attr("placeholder", null);
				select.find("option[value='" + id + "']").attr("selected", "selected")
				hide_error(input);
			}

			function recreate() {
				selector.find("span").remove();
				select.find("option").each(function() {
					if (this.hasAttribute("selected")) {
						addTag(lookup[this.getAttribute("value")]);
					}
				});
			}
			recreate();

			input.focusout(function() {
				const value = input.val().trim();
				if (value !== "") {
					show_error(input, "Please select one of the suggestions, it's not possible to add custom ones.");
				}
			})

			input.keydown(function(e) {
				if (e.keyCode === $.ui.keyCode.TAB && $(this).data('ui-autocomplete').menu.active) {
					e.preventDefault();
				}
			}).autocomplete({
				minLength: 0,
				source: source,
				select: function(event, ui) {
					if (!select.find(`option[value='${ui.item.id}'][selected]`).length) {
						addTag(ui.item);
					}
					input.val("");
					return false;
				}
			}).focus(function() {
				$(this).data("ui-autocomplete").search($(this).val());
			});

			input.data('ui-autocomplete')._renderItem = function(ul, item) {
				return $('<li/>')
					.data('item.autocomplete', item)
					.append($('<a/>').html(item.toString()))
					.appendTo(ul);
			};

			input.data('ui-autocomplete')._resizeMenu = function() {
				const ul = this.menu.element;
				ul.outerWidth(Math.max(
					ul.width('').outerWidth(),
					selector.outerWidth()
				));
			};
		});
	}

	$(function() {
		$(".multichoice_selector").each(function() {
			const ele = $(this);
			const sel = ele.parent().find("select");
			sel.hide();

			const options = [];
			sel.find("option").each(function() {
				const text = $(this).text();
				const option = {
					id: $(this).attr("value"),
					text: text,
					selected: !!$(this).attr("selected"),
					toString: function() { return make_bold(text); },
				};

				const idx = text.indexOf(":");
				if (idx > 0) {
					option.title = text.substring(0, idx);
					option.description = text.substring(idx + 1);
				} else {
					option.title = text
				}

				options.push(option);
			});

			ele.selectSelector(options, sel);
		});
	});
})(jQuery);
