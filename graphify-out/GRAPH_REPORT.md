# Graph Report - The-Stitches  (2026-10-08)

## Corpus Check
- 138 files · ~222,985 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 52 file(s) not represented in the graph (top: .xml 41, (none) 4, .properties 2)

## Summary
- 2336 nodes · 5150 edges · 193 communities (96 shown, 97 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 277 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `40d7abc8`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- uninstaller/updates.py
- info
- uninstaller/diagnose.py
- Ui.kt
- Stitches main README
- make_icon.py
- stitches/gui.py
- StitchesWindow
- stitches/diagnose.py
- uninstaller/widgets.py
- UninstallPage
- stitches/drivers.py
- stitches/cleanup.py
- UninstallPage.kt
- store_backend.py
- HomePage
- stitches/updates.py
- role
- App
- uninstaller/pages/diagnose.py
- px
- UninstallPage
- vitals.py
- Rounded
- uninstaller/cleanup.py
- MainActivity
- Scanner.kt
- Risk
- App
- install
- linux/tests/test_core.py
- strong
- uninstaller/gui.py
- Stitches (Linux 0.2)
- ActionBar
- UpdatesPage
- uninstaller/pages/defrag.py
- UninstallPage
- stitches/selfupdate.py
- uninstaller/models.py
- Permissions.kt
- format_size
- stitches/sysinfo.py
- CoreTest
- ActionBar
- Android port (android/)
- windows/tests/test_core.py
- CoreTest.kt
- uninstaller/uninstaller.py
- Source
- AppsPage
- stitches/appmanager.py
- DefragPage
- DriversPage
- uninstaller/webapps.py
- IconButton
- Risk heuristic, not a dependency graph
- Windows: the Stitches design and tools (0.2.0)
- stitches/uninstaller.py
- The Stitches design (Android)
- Leftovers: AppData/ProgramData, not Documents or registry
- wine_backend.py
- stitches/webapps.py
- stitches/php.py
- _box
- .scan
- choco_backend.py
- .scan
- Privilege escalation: the system's own uninstall dialog
- apt-mark showmanual over full dpkg list
- Linux Uninstaller Main Window Mockup
- Device Diagnostics Symbolic Icon
- Fourth round fix: icon not showing (icon-cache mtime)
- Planned: RPM/Fedora backend
- install.sh
- uninstall.sh
- Planned: Android cache-only cleanup for kept apps
- Planned: AppImage update formats beyond gh-releases-zsync
- Planned: refresh APT index from Updates page
- Planned: code signing for .exe and .msi
- Planned: download size for APT updates
- Planned: load fan sensor chip driver (nct6775/it87)
- Planned: Flatpak release package
- Planned: file-system checks for btrfs/XFS
- Planned: sfc /verifyonly as a real check when already admin
- Planned: one password prompt for all admin Cleanup locations
- Planned: size for Store/Chocolatey/Scoop items
- Planned: SMART self-test button via UDisks2
- Planned: count badges on Windows Updates/Drivers dock buttons
- Planned: Windows Temp and Delivery Optimization cache in Cleanup
- SRS: Linux the Uninstaller
- Attach to the release step (Android)
- Build the APK step
- Attach to the release step (Linux)
- Attach to the release step (Windows)
- stitches
- stitches-windows
- DatabasePanel
- uninstaller/pages/webapps.py
- Health.kt
- AppsPage
- uninstaller/appmanager.py
- elevate.py
- WebAppsPage
- uninstaller/databases.py
- stitches/databases.py
- _client
- uninstaller/drivers.py
- What You Must Do When Invoked
- make_logo.py
- parse_listing
- Install
- powershell
- .__init__
- /graphify
- Postgres
- Terminal
- graphify reference: extra exports and benchmark
- Ponytail
- MySQL
- _pg_id
- _pg_id
- Ponytail Help
- uninstaller/backends/base.py
- MySQL
- Postgres
- stitches/backends/base.py
- Cluster
- graphify reference: query, path, explain
- service_state
- Health
- ponytail-audit/SKILL.md
- Ponytail Gain
- ponytail-review/SKILL.md
- StitchesApp
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- ponytail-debt/SKILL.md
- simplify
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- CLAUDE.md
- extraction-spec.md

## God Nodes (most connected - your core abstractions)
1. `px()` - 93 edges
2. `esc()` - 47 edges
3. `label()` - 46 edges
4. `role()` - 45 edges
5. `UninstallPage` - 41 edges
6. `strong()` - 40 edges
7. `Rounded` - 39 edges
8. `App` - 36 edges
9. `AppsPage` - 32 edges
10. `App` - 32 edges

## Surprising Connections (you probably didn't know these)
- `Interpreter guard for subcommands` --references--> `path()`  [INFERRED]
  .claude/skills/graphify/SKILL.md → android/tools/make_logo.py
- `Safe/Caution/Critical risk rating (Android)` --semantically_similar_to--> `Safe/Caution/Critical risk rating (Windows)`  [INFERRED] [semantically similar]
  android/README.md → windows/README.md
- `Safe/Caution/Critical risk rating (Linux)` --semantically_similar_to--> `Safe/Caution/Critical risk rating (Android)`  [INFERRED] [semantically similar]
  README.md → android/README.md
- `Safe/Caution/Critical risk rating (Linux)` --semantically_similar_to--> `Safe/Caution/Critical risk rating (Windows)`  [INFERRED] [semantically similar]
  README.md → windows/README.md
- `Self-update download-then-verify mechanism (Linux/root)` --semantically_similar_to--> `Self-update download-then-verify mechanism (Windows)`  [INFERRED] [semantically similar]
  README.md → windows/README.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Trust the authoritative state (dpkg status / registry key / package manager) over a process exit code** — documents_ai_knowledgebase_apt_nonzero_exit_fix, documents_ai_knowledgebase_windows_risk_heuristic, documents_ai_knowledgebase_android_did_it_go [EXTRACTED 0.90]
- **Use the platform's own already-installed UI toolkit (GTK3 / tkinter / android.widget)** — documents_ai_knowledgebase_stack_choice, documents_ai_knowledgebase_windows_gui_tkinter, documents_ai_knowledgebase_android_kotlin_no_androidx [EXTRACTED 0.95]
- **CLAUDE.md privilege-escalation non-negotiable, realized per platform (pkexec / ShellExecuteEx+runas / system uninstall dialog)** — documents_ai_knowledgebase_pkexec_privilege_escalation, documents_ai_knowledgebase_windows_privilege_escalation, documents_ai_knowledgebase_android_privilege_escalation [EXTRACTED 0.95]
- **Parallel multi-platform tag-triggered release** — github_workflows_linux_build_workflow, github_workflows_windows_build_workflow, github_workflows_android_build_workflow [EXTRACTED 1.00]
- **Stitches Cross-Platform Hourglass/Uninstall Branding** — linux_src_stitches_icon_app_icon, windows_src_uninstaller_icon_app_icon, linux_src_stitches_icons_stitches_uninstall_symbolic_uninstall_icon [INFERRED 0.75]
- **Safe/Caution/Critical risk rating pattern shared across platforms** — readme_risk_rating, android_readme_risk_rating, windows_readme_risk_rating [INFERRED 0.85]
- **Stitches Linux GTK Symbolic Icon Set** — linux_src_stitches_icons_cpu_symbolic_cpu_icon, linux_src_stitches_icons_device_diagnostics_symbolic_diagnostics_icon, linux_src_stitches_icons_memory_symbolic_memory_icon, linux_src_stitches_icons_sensors_temperature_symbolic_temperature_icon, linux_src_stitches_icons_stitches_uninstall_symbolic_uninstall_icon, linux_src_stitches_icons_tool_brush_symbolic_brush_icon [INFERRED 0.85]
- **Non-negotiable safety rails implemented per platform** — claude_non_negotiables, readme_doc, android_readme_doc, windows_readme_doc [INFERRED 0.85]

## Communities (193 total, 97 thin omitted)

### Community 0 - "uninstaller/updates.py"
Cohesion: 0.18
Nodes (15): apply(), build_wu_updates(), _choco_updates(), find_updates(), parse_choco_outdated(), parse_scoop_status(), parse_winget(), plan_jobs() (+7 more)

### Community 1 - "info"
Cohesion: 0.06
Nodes (12): tail(), format_size(), CleanupPage, work(), log(), DriversPage, UpdatesPage, work() (+4 more)

### Community 2 - "uninstaller/diagnose.py"
Cohesion: 0.06
Nodes (41): Check, component_store(), count_events(), disk_health(), failed_services(), file_systems(), Fix, free_space() (+33 more)

### Community 3 - "Ui.kt"
Cohesion: 0.09
Nodes (4): HomePage, PageBar, tag(), TagSpan

### Community 4 - "Stitches main README"
Cohesion: 0.07
Nodes (33): build-apk.sh script, Stitches for Android README, Safe/Caution/Critical risk rating (Android), Test section (Android), CLAUDE.md project instructions, graphify usage rules, documents/ai-knowledgebase.md, documents/features.md (+25 more)

### Community 5 - "make_icon.py"
Cohesion: 0.14
Nodes (10): Shared hand-drawn icon.svg source for all platform icons, border_points(), cubic(), dashes(), _downsample(), main(), png(), render() (+2 more)

### Community 6 - "stitches/gui.py"
Cohesion: 0.08
Nodes (16): AboutPage, _status(), _section(), _marked(), arrow(), card(), esc(), icon_button() (+8 more)

### Community 8 - "stitches/diagnose.py"
Cohesion: 0.13
Nodes (23): Check, _check_at_restart(), disk_health(), file_systems(), Fix, free_space(), logged_errors(), memory_at_restart() (+15 more)

### Community 9 - "uninstaller/widgets.py"
Cohesion: 0.09
Nodes (11): _disc(), _drain(), fit_text(), _mask(), mix(), picture(), _quarter(), _rgb() (+3 more)

### Community 11 - "stitches/drivers.py"
Cohesion: 0.11
Nodes (18): apply(), changelog_date(), command_for(), dmi_date(), Driver, find_drivers(), firmware_purpose(), gpu_name() (+10 more)

### Community 12 - "stitches/cleanup.py"
Cohesion: 0.13
Nodes (17): _apt_cache(), _children(), clean(), _files_size(), _flatpak_unused(), is_stale(), _journal(), Location (+9 more)

### Community 13 - "UninstallPage.kt"
Cohesion: 0.08
Nodes (9): afterTextChanged(), AppAdapter, bulkPickable(), onItemSelected(), onNothingSelected(), Ticked, ALL, NONE (+1 more)

### Community 14 - "store_backend.py"
Cohesion: 0.23
Nodes (5): build_apps(), parse_appx_csv(), _truthy(), classify_store_package(), test_appx_parse_and_framework_detection()

### Community 15 - "HomePage"
Cohesion: 0.22
Nodes (4): _bar(), _clear(), _column(), HomePage

### Community 16 - "stitches/updates.py"
Cohesion: 0.10
Nodes (23): installed_packages(), parse_snap_list(), output(), apply(), _apt_updates(), command_for(), download(), find_updates() (+15 more)

### Community 17 - "role"
Cohesion: 0.09
Nodes (10): AboutPage, _clear(), HomePage, _note(), _tag(), filter_pill(), Icon, on_theme() (+2 more)

### Community 18 - "App"
Cohesion: 0.12
Nodes (14): AptBackend, build_apps(), parse_showmanual(), build_apps(), FlatpakBackend, parse_flatpak_list(), parse_size(), LocalBackend (+6 more)

### Community 19 - "uninstaller/pages/diagnose.py"
Cohesion: 0.09
Nodes (7): DiagnosePage, resized(), work(), work(), Dialog, status_label(), Terminal

### Community 20 - "px"
Cohesion: 0.09
Nodes (5): draw_tag(), os_switch(), px(), Table, Tiles

### Community 22 - "vitals.py"
Cohesion: 0.09
Nodes (22): defrag(), Drive, find_drives(), os_of(), parse_lsblk(), walk(), plan(), chip_label() (+14 more)

### Community 23 - "Rounded"
Cohesion: 0.16
Nodes (3): _card(), Button, Rounded

### Community 24 - "uninstaller/cleanup.py"
Cohesion: 0.17
Nodes (12): install_roots(), browser_caches(), _children(), clean(), is_stale(), Location, _one(), _recycle_bin_size() (+4 more)

### Community 26 - "Scanner.kt"
Cohesion: 0.13
Nodes (5): hasUsageAccess(), Scanner, SizeReader, installerLabelFor(), sourceFor()

### Community 27 - "Risk"
Cohesion: 0.20
Nodes (8): build_apps(), Risk, Source, classify_apt(), classify_default(), classify_local(), classify_runtime_name(), test_classify_apt()

### Community 28 - "App"
Cohesion: 0.12
Nodes (15): ChocoBackend, build_apps(), is_listable(), read_uninstall_entries(), _read_view(), RegistryBackend, registered(), uninstall_command_line() (+7 more)

### Community 29 - "install"
Cohesion: 0.14
Nodes (7): install(), install_kind(), _kind(), pick_asset(), restart(), tidy(), download()

### Community 30 - "linux/tests/test_core.py"
Cohesion: 0.07
Nodes (6): parse_dpkg_query(), _elf_with_update_info(), test_appimage_update_info(), test_dpkg_query_parse(), test_snap_list_parse_and_runtime_detection(), test_update_jobs_batch_password_sources()

### Community 31 - "strong"
Cohesion: 0.07
Nodes (10): DatabasePanel, work(), _form(), _new_password(), DiagnosePage, work(), tail(), confirm() (+2 more)

### Community 32 - "uninstaller/gui.py"
Cohesion: 0.09
Nodes (7): ico_pictures(), _load_settings(), main(), _save_settings(), _system_theme(), UninstallerWindow, set_theme()

### Community 33 - "Stitches (Linux 0.2)"
Cohesion: 0.10
Nodes (6): Stitches (Linux 0.2), Features, Planned: fragmentation analysis before defrag, Done: Stitches 0.2 fifth round, Done: Stitches 0.2 (first round / rename), Done: Stitches 0.2 third round

### Community 34 - "ActionBar"
Cohesion: 0.17
Nodes (3): ActionBar, tick(), worker()

### Community 36 - "uninstaller/pages/defrag.py"
Cohesion: 0.17
Nodes (3): DefragPage, Tick, Tooltip

### Community 38 - "stitches/selfupdate.py"
Cohesion: 0.11
Nodes (11): install(), install_kind(), is_newer(), latest(), parse_version(), pick_asset(), restart(), is_newer() (+3 more)

### Community 39 - "uninstaller/models.py"
Cohesion: 0.21
Nodes (7): build_apps(), build_apps(), Risk, Source, classify_installer(), classify_managed_package(), test_classify_installer()

### Community 40 - "Permissions.kt"
Cohesion: 0.16
Nodes (5): allFilesAccessIntent(), usageAccessIntent(), leftoversFor(), removalIntent(), removalOutcome()

### Community 41 - "format_size"
Cohesion: 0.16
Nodes (4): format_size(), CleanupPage, work(), _pretty()

### Community 42 - "stitches/sysinfo.py"
Cohesion: 0.15
Nodes (11): describe_firmware(), disk_label(), _disks(), parse_cpuinfo(), parse_meminfo(), parse_os_release(), pick_board(), _read() (+3 more)

### Community 43 - "CoreTest"
Cohesion: 0.24
Nodes (4): classify(), RiskSignals, RiskVerdict, CoreTest

### Community 44 - "ActionBar"
Cohesion: 0.17
Nodes (6): work(), ActionBar, tick(), tick(), tick(), worker()

### Community 45 - "Android port (android/)"
Cohesion: 0.14
Nodes (6): Android port (android/), Themes: Light, Dark, AMOLED, Glass, Windows port (windows/), Done: Android feature checklist, Planned: Play-flavoured Android build, Done: Windows feature checklist

### Community 46 - "windows/tests/test_core.py"
Cohesion: 0.11
Nodes (3): split_command(), test_registry_build_apps(), test_split_command()

### Community 47 - "CoreTest.kt"
Cohesion: 0.19
Nodes (6): deletePaths(), findLeftovers(), pathSize(), scanRoots(), searchTerms(), cleanLeftovers()

### Community 48 - "uninstaller/uninstaller.py"
Cohesion: 0.18
Nodes (8): delete_paths(), find_leftovers(), scan_roots(), work(), backend_for(), clean_leftovers(), uninstall(), test_leftovers_name_match()

### Community 49 - "Source"
Cohesion: 0.18
Nodes (11): App, Risk, CAUTION, CRITICAL, SAFE, Source, FDROID, OTHER_STORE (+3 more)

### Community 50 - "AppsPage"
Cohesion: 0.10
Nodes (3): AppsPage, _combo(), PhpPanel

### Community 51 - "stitches/appmanager.py"
Cohesion: 0.08
Nodes (18): _add_repo(), check(), command_for(), _command_version(), detect(), _extra_paths(), find_command(), install() (+10 more)

### Community 54 - "uninstaller/webapps.py"
Cohesion: 0.09
Nodes (26): Browser, browser_args(), create(), _data_dir(), favicon_service(), fetch_meta(), find_browsers(), _get() (+18 more)

### Community 55 - "IconButton"
Cohesion: 0.14
Nodes (3): _blank(), IconButton, _over()

### Community 56 - "Risk heuristic, not a dependency graph"
Cohesion: 0.20
Nodes (4): Done: Linux v0.1 feature checklist, Planned: reverse-dependency check for apt packages, Non-functional Requirements, Risk classification: Safe/Caution/Critical

### Community 57 - "Windows: the Stitches design and tools (0.2.0)"
Cohesion: 0.20
Nodes (3): Windows: the Stitches design and tools (0.2.0), Planned: bring Android build the new tools, Done: Windows Stitches design and tools (0.2.0)

### Community 58 - "stitches/uninstaller.py"
Cohesion: 0.27
Nodes (5): find_leftovers(), backend_for(), clean_leftovers(), uninstall(), test_leftovers_name_match()

### Community 59 - "The Stitches design (Android)"
Cohesion: 0.22
Nodes (3): The Stitches design (Android), Done: Android Stitches design, Done: Stitches 0.2 second round

### Community 60 - "Leftovers: AppData/ProgramData, not Documents or registry"
Cohesion: 0.22
Nodes (5): Planned: split Android leftover scan by confidence, Planned: package-manager-owned leftovers under /etc, Planned: per-app Program Files leftovers, Planned: registry leftovers (orphaned HKCU keys), Functional Requirements FR1-FR9

### Community 61 - "wine_backend.py"
Cohesion: 0.25
Nodes (5): build_apps(), find_prefixes(), parse_uninstall_keys(), _unescape(), test_wine_uninstall_key_parse()

### Community 62 - "stitches/webapps.py"
Cohesion: 0.10
Nodes (23): _apps_dir(), Browser, create(), _data_dir(), desktop_entry(), desktop_quote(), favicon_service(), fetch_meta() (+15 more)

### Community 63 - "stitches/php.py"
Cohesion: 0.09
Nodes (18): _active(), apply(), apply_command(), changes(), default_version(), enabled_in(), Extension, extensions() (+10 more)

### Community 64 - "_box"
Cohesion: 0.25
Nodes (6): _box(), _line(), inside(), _triangle(), inside(), side()

### Community 65 - ".scan"
Cohesion: 0.33
Nodes (3): parse_manifest(), read_packages(), test_scoop_manifest_and_directory_scan()

### Community 66 - "choco_backend.py"
Cohesion: 0.27
Nodes (4): install_root(), parse_nuspec(), read_packages(), test_nuspec_parse_and_manager_is_critical()

### Community 67 - ".scan"
Cohesion: 0.40
Nodes (3): install_paths(), _version(), test_local_install_and_driver_purpose()

### Community 70 - "Linux Uninstaller Main Window Mockup"
Cohesion: 0.50
Nodes (5): Linux Uninstaller Main Window Mockup, Stitches Linux App Icon (Stitched Hourglass), Stitches Uninstall Action Symbolic Icon, Tool Brush Symbolic Icon, Stitches Windows Uninstaller App Icon (Hourglass)

### Community 72 - "Device Diagnostics Symbolic Icon"
Cohesion: 0.50
Nodes (4): CPU Symbolic Icon, Device Diagnostics Symbolic Icon, Memory (RAM) Symbolic Icon, Temperature Sensor Symbolic Icon

### Community 146 - "DatabasePanel"
Cohesion: 0.11
Nodes (4): DatabasePanel, work(), _form(), _new_password()

### Community 147 - "uninstaller/pages/webapps.py"
Cohesion: 0.15
Nodes (6): _field(), _photo(), _shrunk(), _square_png(), WebAppsPage, recolour()

### Community 148 - "Health.kt"
Cohesion: 0.19
Nodes (14): batteryFinding(), debuggingFinding(), encryptionFinding(), Finding, healthCheck(), integrityFinding(), lockFinding(), memoryFinding() (+6 more)

### Community 149 - "AppsPage"
Cohesion: 0.13
Nodes (3): AppsPage, log(), work()

### Community 150 - "uninstaller/appmanager.py"
Cohesion: 0.15
Nodes (14): check(), _command_version(), detect(), install(), install_command(), installed_packages(), is_store_stub(), manual_steps() (+6 more)

### Community 151 - "elevate.py"
Cohesion: 0.14
Nodes (12): clean_output(), elevated_cmd_params(), family_of(), is_admin(), _process_table(), run(), _run_elevated(), _stream() (+4 more)

### Community 152 - "WebAppsPage"
Cohesion: 0.15
Nodes (5): _emoji_png(), _pixbuf(), _ready_icons(), _square_png(), WebAppsPage

### Community 153 - "uninstaller/databases.py"
Cohesion: 0.18
Nodes (12): _my_account(), my_create_database(), my_create_user(), my_drop_database(), my_drop_user(), _my_id(), my_password(), _my_str() (+4 more)

### Community 154 - "stitches/databases.py"
Cohesion: 0.18
Nodes (11): _my_account(), my_create_database(), my_create_user(), my_drop_database(), my_drop_user(), _my_id(), my_password(), _my_str() (+3 more)

### Community 155 - "_client"
Cohesion: 0.15
Nodes (8): _client(), Database, Listing, my_option_file(), parse_listing(), restart(), _then_list(), User

### Community 156 - "uninstaller/drivers.py"
Cohesion: 0.21
Nodes (10): Driver, is_hardware(), merge(), parse_devices(), purpose(), scan(), update(), version_from_title() (+2 more)

### Community 157 - "What You Must Do When Invoked"
Cohesion: 0.13
Nodes (15): Part A - Structural extraction for code files, Part B - Semantic extraction (parallel subagents), Part C - Merge AST + semantic into final extraction, Step 0 - GitHub repos and multi-path merge (only if a URL or several paths), Step 1 - Ensure graphify is installed, Step 2.5 - Video and audio (only if video files detected), Step 2 - Detect files, Step 3 - Extract entities and relationships (+7 more)

### Community 158 - "make_logo.py"
Cohesion: 0.23
Nodes (9): border_points(), cubic(), dashes(), main(), path(), path_data(), simplify(), thread_points() (+1 more)

### Community 159 - "parse_listing"
Cohesion: 0.21
Nodes (5): _client(), Database, Listing, parse_listing(), User

### Community 160 - "Install"
Cohesion: 0.18
Nodes (5): find_client(), Install, _mysql_folders(), pg_installs(), _registry_values()

### Community 161 - "powershell"
Cohesion: 0.30
Nodes (8): _int(), optimize(), optimize_script(), parse_volumes(), plan(), scan(), Volume, powershell()

### Community 162 - ".__init__"
Cohesion: 0.20
Nodes (5): _find_theme_variant(), _list_installed_themes(), _load_settings(), _save_settings(), _strip_theme_variant()

### Community 163 - "/graphify"
Cohesion: 0.20
Nodes (9): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Usage (+1 more)

### Community 164 - "Postgres"
Cohesion: 0.20
Nodes (3): parse_unit(), Postgres, _unit_state()

### Community 166 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 167 - "Ponytail"
Cohesion: 0.22
Nodes (8): Boundaries, Intensity, Output, Persistence, Ponytail, Rules, The ladder, When NOT to be lazy

### Community 169 - "_pg_id"
Cohesion: 0.28
Nodes (7): pg_create_database(), pg_create_user(), pg_drop_database(), pg_drop_user(), _pg_id(), pg_password(), scram()

### Community 170 - "_pg_id"
Cohesion: 0.28
Nodes (7): pg_create_database(), pg_create_user(), pg_drop_database(), pg_drop_user(), _pg_id(), pg_password(), scram()

### Community 171 - "Ponytail Help"
Cohesion: 0.25
Nodes (7): Configure Default Mode, Deactivate, Levels, More, Ponytail Help, Skills, Update

### Community 176 - "Cluster"
Cohesion: 0.33
Nodes (3): Cluster, parse_clusters(), pg_clusters()

### Community 177 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 179 - "Health"
Cohesion: 0.40
Nodes (5): Health, INFO, OK, PROBLEM, WARNING

### Community 180 - "ponytail-audit/SKILL.md"
Cohesion: 0.40
Nodes (4): Boundaries, Hunt, Output, Tags

### Community 181 - "Ponytail Gain"
Cohesion: 0.40
Nodes (4): Boundaries, Honesty boundary, Ponytail Gain, Scoreboard

### Community 182 - "ponytail-review/SKILL.md"
Cohesion: 0.40
Nodes (4): Boundaries, Examples, Format, Scoring

### Community 184 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 185 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 186 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 187 - "ponytail-debt/SKILL.md"
Cohesion: 0.50
Nodes (3): Boundaries, Output, Scan

## Ambiguous Edges - Review These
- `Planned: bring Android build the new tools` → `Windows: the Stitches design and tools (0.2.0)`  [AMBIGUOUS]
  documents/features.md · relation: references
- `Linux Uninstaller Main Window Mockup` → `Tool Brush Symbolic Icon`  [AMBIGUOUS]
  linux/src/stitches/icons/tool-brush-symbolic.svg · relation: conceptually_related_to

## Knowledge Gaps
- **151 isolated node(s):** `OK`, `WARNING`, `PROBLEM`, `INFO`, `PLAY` (+146 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 848 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **97 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Planned: bring Android build the new tools` and `Windows: the Stitches design and tools (0.2.0)`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `Linux Uninstaller Main Window Mockup` and `Tool Brush Symbolic Icon`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `px()` connect `px` to `uninstaller/gui.py`, `info`, `uninstaller/pages/defrag.py`, `uninstaller/widgets.py`, `UninstallPage`, `ActionBar`, `role`, `DatabasePanel`, `uninstaller/pages/diagnose.py`, `uninstaller/pages/webapps.py`, `AppsPage`, `IconButton`, `Rounded`?**
  _High betweenness centrality (0.043) - this node is a cross-community bridge._
- **Why does `later()` connect `info` to `uninstaller/gui.py`, `uninstaller/widgets.py`, `UninstallPage`, `ActionBar`, `uninstaller/uninstaller.py`, `role`, `uninstaller/pages/diagnose.py`, `AppsPage`, `Rounded`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `Page` connect `info` to `uninstaller/pages/defrag.py`, `uninstaller/widgets.py`, `UninstallPage`, `ActionBar`, `role`, `uninstaller/pages/diagnose.py`, `uninstaller/pages/webapps.py`, `AppsPage`, `IconButton`, `Rounded`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `UninstallPage` (e.g. with `UninstallerWindow` and `Risk`) actually correct?**
  _`UninstallPage` has 7 INFERRED edges - model-reasoned connections that need verification._
- **What connects `OK`, `WARNING`, `PROBLEM` to the rest of the system?**
  _151 weakly-connected nodes found - possible documentation gaps or missing edges._