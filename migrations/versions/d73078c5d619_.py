"""empty message

Revision ID: d73078c5d619
Revises: 6a0aee983614
Create Date: 2024-02-25 15:41:56.617594

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'd73078c5d619'
down_revision = '6a0aee983614'
branch_labels = None
depends_on = None


def upgrade():
	# Source: https://github.com/luanti-org/luanti/blob/master/builtin/mainmenu/settings/dlg_settings.lua#L156
	languages = {
		"en": "English",
		# "ar": "", blacklisted
		"be": "Беларуская",
		"bg": "Български",
		"ca": "Català",
		"cs": "Česky",
		"cy": "Cymraeg",
		"da": "Dansk",
		"de": "Deutsch",
		# "dv": "", blacklisted
		"el": "Ελληνικά",
		"eo": "Esperanto",
		"es": "Español",
		"et": "Eesti",
		"eu": "Euskara",
		"fi": "Suomi",
		"fil": "Wikang Filipino",
		"fr": "Français",
		"gd": "Gàidhlig",
		"gl": "Galego",
		# "he": "", blacklisted
		# "hi": "", blacklisted
		"hu": "Magyar",
		"id": "Bahasa Indonesia",
		"it": "Italiano",
		"ja": "日本語",
		"jbo": "Lojban",
		"kk": "Қазақша",
		# "kn": "", blacklisted
		"ko": "한국어",
		"ky": "Kırgızca / Кыргызча",
		"lt": "Lietuvių",
		"lv": "Latviešu",
		"mn": "Монгол",
		"mr": "मराठी",
		"ms": "Bahasa Melayu",
		# "ms_Arab": "", blacklisted
		"nb": "Norsk Bokmål",
		"nl": "Nederlands",
		"nn": "Norsk Nynorsk",
		"oc": "Occitan",
		"pl": "Polski",
		"pt": "Português",
		"pt_BR": "Português do Brasil",
		"ro": "Română",
		"ru": "Русский",
		"sk": "Slovenčina",
		"sl": "Slovenščina",
		"sr_Cyrl": "Српски",
		"sr_Latn": "Srpski (Latinica)",
		"sv": "Svenska",
		"sw": "Kiswahili",
		# "th": "", blacklisted
		"tr": "Türkçe",
		"tt": "Tatarça",
		"uk": "Українська",
		"vi": "Tiếng Việt",
		"zh_CN": "中文 (简体)",
		"zh_TW": "正體中文 (繁體)",
	}

	bind = op.get_bind()
	for id_, title in languages.items():
		bind.execute(text("INSERT INTO language(id, title) VALUES (:id, :title)"), {
			"id": id_,
			"title": title,
		})


def downgrade():
	pass
