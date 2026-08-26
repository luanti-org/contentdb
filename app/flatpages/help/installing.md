title: How to install mods, games, and texture packs
description: A guide to installing mods, games, and texture packs in Luanti.

## Installing from the main menu (recommended)

### Install

1. Open the mainmenu
2. Go to the Content tab and click "Browse online content".
   If you don't see this, then you need to update Luanti to v5.
3. Search for the package you want to install, and click "Install".
4. When installing a mod, you may be shown a dialog about dependencies here.
   Make sure the base game dropdown box is correct, and then click "Install".

<div class="row mt-5">
  <div class="col-md-6">
    <figure>
      <a href="/static/installing_content_tab.png">
        <img class="w-100" src="/static/installing_content_tab.png" alt="Screenshot of the content tab in Luanti">
      </a>
      <figcaption class="text-muted ps-1">
        1. Click Browser Online Content in the content tab.
      </figcaption>
    </figure>
  </div>
  <div class="col-md-6">
    <figure>
      <a href="/static/installing_cdb_dialog.png">
        <img class="w-100" src="/static/installing_cdb_dialog.png" alt="Screenshot of the content tab in Luanti">
      </a>
      <figcaption class="text-muted ps-1">
        2. Search for the package and click "Install".
      </figcaption>
    </figure>
  </div>
</div>

Troubleshooting:

* I can't find it in the ContentDB dialog (Browse online content)
    * Make sure that you're on the latest version of Luanti.
    * Are you using Android? Packages with content warnings are hidden by default on android,
      you can show them by removing `android_default` from the `contentdb_flag_blacklist` setting.
* It says "required dependencies could not be found"
    * Make sure you're using the correct "Base Game". A lot of packages only work with certain games, you can look
      at "Compatible Games" on the web page to see which.

### Enable in Select Mods

1. Mods: Enable the content using "Select Mods" when selecting a world.
2. Games: choose a game when making a world.
3. Texture packs: Content > Select pack > Click enable.


<div class="row mt-5">
  <div class="col-md-6">
    <figure>
      <a href="/static/installing_select_mods.png">
        <img class="w-100" src="/static/installing_select_mods.png" alt="Screenshot of Select Mods in Luanti">
      </a>
      <figcaption class="text-muted ps-1">
        Enable mods using the Select Mods dialog.
      </figcaption>
    </figure>
  </div>
</div>

## Installing using the command line

### Git clone

1. Install git
2. Find the package on ContentDB and copy "source" link.
3. Find the user data directory.
   In 5.4.0 and above, you can click "Open user data directory" in the Credits tab.
   Otherwise:
     * Windows: wherever you extracted or installed Luanti to.
     * Linux: usually `~/.minetest/`
4. Open or create the folder for the type of content (`mods`, `games`, or `textures`)
5. Git clone there
6. For mods, make sure to install any required dependencies.

### Enable

* Mods: Edit world.mt in the world's folder to contain `load_file_MODNAME = true`
* Games: Use `--game` or edit game_id in world.mt.
* Texture packs: change the `texture_path` setting to the texture pack absolute path.
