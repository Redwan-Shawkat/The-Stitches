# Graph Report - The-Stitches  (2026-10-03)

## Corpus Check
- 115 files · ~99,651 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 52 file(s) not represented in the graph (top: .xml 41, (none) 4, .properties 2)

## Summary
- 1671 nodes · 3648 edges · 146 communities (61 shown, 85 thin omitted)
- Extraction: 94% EXTRACTED · 6% INFERRED · 0% AMBIGUOUS · INFERRED: 222 edges (avg confidence: 0.89)
- Token cost: 355,501 input · 0 output

## Community Hubs (Navigation)
- Windows Defrag Engine
- Windows App Entry & Pages
- Windows Diagnose Checks
- Android Health Check
- Android Docs & Build
- Icon & Logo Generators
- Linux App Package
- Linux GTK Main Window
- Linux Diagnose Checks
- Windows Tk Widgets
- Windows Uninstall Select-All
- Linux Driver Updates
- Linux Cleanup Engine
- Android Uninstall List
- Windows Backend Base
- Windows Grouped Cards
- Linux Snap Parsing
- Windows Home Page
- Linux APT Backend
- Page Background Work
- Canvas Tags & Text Fit
- Uninstall Table Filtering
- Linux Vitals Sensors
- Windows GUI Shell & Theme
- Windows Cleanup Engine
- Android Main Activity
- Android App Scanner
- Linux Flatpak Backend
- Windows Registry Backend
- Windows Self-Update & Launch
- Flatpak List Parsing
- Page Done Callbacks
- Windows Icon Dock
- Linux Feature Decisions
- Linux Action Bar & Toast
- Windows Updates Table
- Windows Defrag Page
- Android Uninstall Flow
- Linux Self-Update
- Chocolatey & Scoop Backends
- Android Permissions
- Linux Cleanup Page
- Linux System Info
- Android Risk Classifier
- Progress Bar Animation
- Android Port Decisions
- Windows Test Suite
- Android Leftover Scan
- Windows Leftover Scan
- Android Data Models
- Linux Defrag Engine
- APT Parsing & Risk
- Linux Defrag Page
- Linux Drivers Page
- Linux Page Widgets
- Windows Icon Button
- Cross-Platform Safety Principles
- Windows Port Decisions
- Linux Uninstall & Leftovers
- Android Health & Icon Decisions
- Android Leftover Decisions
- Wine Backend
- GitHub/AppImage Updates
- Filter Pills
- Canvas Stroke Primitives
- Scoop Manifest Parsing
- Chocolatey Nuspec Parsing
- Local Install Backend
- Privilege Escalation per OS
- Read-State-Not-CLI Decisions
- App Icon & Mockup
- Diagnostics Symbolic Icons
- Linux Icon Cache Fix
- Scope & RPM Plan
- Linux install.sh
- Linux uninstall.sh
- Planned: Android cache-only cleanup for
- Planned: AppImage update formats beyond
- Planned: refresh APT index from
- Planned: code signing for .exe
- Planned: download size for APT
- Planned: load fan sensor chip
- Planned: Flatpak release package
- Planned: file-system checks for btrfs/XFS
- Planned: sfc /verifyonly as a
- Planned: one password prompt for
- Planned: size for Store/Chocolatey/Scoop items
- Planned: SMART self-test button via
- Planned: count badges on Windows
- Planned: Windows Temp and Delivery
- SRS: Linux the Uninstaller
- Attach to the release step
- Build the APK step
- Attach to the release step
- Attach to the release step
- stitches
- stitches-windows

## God Nodes (most connected - your core abstractions)
1. `px()` - 59 edges
2. `UninstallPage` - 41 edges
3. `App` - 36 edges
4. `App` - 32 edges
5. `strong()` - 28 edges
6. `Table` - 28 edges
7. `UninstallPage` - 27 edges
8. `Risk` - 27 edges
9. `UninstallPage` - 27 edges
10. `esc()` - 26 edges

## Surprising Connections (you probably didn't know these)
- `Safe/Caution/Critical risk rating (Linux)` --semantically_similar_to--> `Safe/Caution/Critical risk rating (Android)`  [INFERRED] [semantically similar]
  README.md → android/README.md
- `Safe/Caution/Critical risk rating (Linux)` --semantically_similar_to--> `Safe/Caution/Critical risk rating (Windows)`  [INFERRED] [semantically similar]
  README.md → windows/README.md
- `Safe/Caution/Critical risk rating (Android)` --semantically_similar_to--> `Safe/Caution/Critical risk rating (Windows)`  [INFERRED] [semantically similar]
  android/README.md → windows/README.md
- `Self-update download-then-verify mechanism (Linux/root)` --semantically_similar_to--> `Self-update download-then-verify mechanism (Windows)`  [INFERRED] [semantically similar]
  README.md → windows/README.md
- `Stitches Windows Uninstaller App Icon (Hourglass)` --semantically_similar_to--> `Stitches Linux App Icon (Stitched Hourglass)`  [INFERRED] [semantically similar]
  windows/src/uninstaller/icon.svg → linux/src/stitches/icon.svg

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Use the platform's own already-installed UI toolkit (GTK3 / tkinter / android.widget)** — documents_ai_knowledgebase_stack_choice, documents_ai_knowledgebase_windows_gui_tkinter, documents_ai_knowledgebase_android_kotlin_no_androidx [EXTRACTED 0.95]
- **Trust the authoritative state (dpkg status / registry key / package manager) over a process exit code** — documents_ai_knowledgebase_apt_nonzero_exit_fix, documents_ai_knowledgebase_windows_risk_heuristic, documents_ai_knowledgebase_android_did_it_go [EXTRACTED 0.90]
- **CLAUDE.md privilege-escalation non-negotiable, realized per platform (pkexec / ShellExecuteEx+runas / system uninstall dialog)** — documents_ai_knowledgebase_pkexec_privilege_escalation, documents_ai_knowledgebase_windows_privilege_escalation, documents_ai_knowledgebase_android_privilege_escalation [EXTRACTED 0.95]
- **Parallel multi-platform tag-triggered release** — github_workflows_linux_build_workflow, github_workflows_windows_build_workflow, github_workflows_android_build_workflow [EXTRACTED 1.00]
- **Safe/Caution/Critical risk rating pattern shared across platforms** — readme_risk_rating, android_readme_risk_rating, windows_readme_risk_rating [INFERRED 0.85]
- **Non-negotiable safety rails implemented per platform** — claude_non_negotiables, readme_doc, android_readme_doc, windows_readme_doc [INFERRED 0.85]
- **Stitches Linux GTK Symbolic Icon Set** — linux_src_stitches_icons_cpu_symbolic_cpu_icon, linux_src_stitches_icons_device_diagnostics_symbolic_diagnostics_icon, linux_src_stitches_icons_memory_symbolic_memory_icon, linux_src_stitches_icons_sensors_temperature_symbolic_temperature_icon, linux_src_stitches_icons_stitches_uninstall_symbolic_uninstall_icon, linux_src_stitches_icons_tool_brush_symbolic_brush_icon [INFERRED 0.85]
- **Stitches Cross-Platform Hourglass/Uninstall Branding** — linux_src_stitches_icon_app_icon, windows_src_uninstaller_icon_app_icon, linux_src_stitches_icons_stitches_uninstall_symbolic_uninstall_icon [INFERRED 0.75]

## Communities (146 total, 85 thin omitted)

### Community 0 - "Windows Defrag Engine"
Cohesion: 0.06
Nodes (45): _int(), optimize(), optimize_script(), parse_volumes(), plan(), scan(), Volume, Driver (+37 more)

### Community 1 - "Windows App Entry & Pages"
Cohesion: 0.06
Nodes (11): tail(), _load_settings(), _save_settings(), format_size(), CleanupPage, DriversPage, UpdatesPage, work() (+3 more)

### Community 2 - "Windows Diagnose Checks"
Cohesion: 0.06
Nodes (40): Check, component_store(), count_events(), disk_health(), failed_services(), file_systems(), Fix, free_space() (+32 more)

### Community 3 - "Android Health Check"
Cohesion: 0.06
Nodes (22): batteryFinding(), debuggingFinding(), encryptionFinding(), Finding, Health, INFO, OK, PROBLEM (+14 more)

### Community 4 - "Android Docs & Build"
Cohesion: 0.07
Nodes (33): build-apk.sh script, Stitches for Android README, Safe/Caution/Critical risk rating (Android), Test section (Android), CLAUDE.md project instructions, graphify usage rules, documents/ai-knowledgebase.md, documents/features.md (+25 more)

### Community 5 - "Icon & Logo Generators"
Cohesion: 0.08
Nodes (21): border_points(), cubic(), dashes(), main(), path(), path_data(), simplify(), thread_points() (+13 more)

### Community 6 - "Linux App Package"
Cohesion: 0.13
Nodes (8): tail(), arrow(), card(), info(), make_table(), scrolled(), show_select_all(), two_lines()

### Community 7 - "Linux GTK Main Window"
Cohesion: 0.11
Nodes (9): _find_theme_variant(), _list_installed_themes(), _load_settings(), main(), _save_settings(), StitchesApp, StitchesWindow, _strip_theme_variant() (+1 more)

### Community 8 - "Linux Diagnose Checks"
Cohesion: 0.12
Nodes (22): Check, _check_at_restart(), disk_health(), file_systems(), Fix, free_space(), logged_errors(), memory_at_restart() (+14 more)

### Community 9 - "Windows Tk Widgets"
Cohesion: 0.09
Nodes (13): _blank(), _disc(), _drain(), Icon, _mask(), mix(), picture(), _quarter() (+5 more)

### Community 11 - "Linux Driver Updates"
Cohesion: 0.11
Nodes (18): apply(), changelog_date(), command_for(), dmi_date(), Driver, find_drivers(), firmware_purpose(), gpu_name() (+10 more)

### Community 12 - "Linux Cleanup Engine"
Cohesion: 0.13
Nodes (17): _apt_cache(), _children(), clean(), _files_size(), _flatpak_unused(), is_stale(), _journal(), Location (+9 more)

### Community 13 - "Android Uninstall List"
Cohesion: 0.08
Nodes (9): afterTextChanged(), AppAdapter, bulkPickable(), onItemSelected(), onNothingSelected(), Ticked, ALL, NONE (+1 more)

### Community 14 - "Windows Backend Base"
Cohesion: 0.11
Nodes (11): Backend, ChocoBackend, ScoopBackend, build_apps(), parse_appx_csv(), StoreBackend, _truthy(), App (+3 more)

### Community 15 - "Windows Grouped Cards"
Cohesion: 0.13
Nodes (10): _status(), CheckRow, _bar(), _clear(), _column(), HomePage, _section(), esc() (+2 more)

### Community 16 - "Linux Snap Parsing"
Cohesion: 0.12
Nodes (16): parse_size(), parse_snap_list(), apply(), _apt_updates(), command_for(), find_updates(), _flatpak_updates(), parse_apt_policy() (+8 more)

### Community 17 - "Windows Home Page"
Cohesion: 0.12
Nodes (7): _clear(), HomePage, _note(), _tag(), on_theme(), role(), status_label()

### Community 18 - "Linux APT Backend"
Cohesion: 0.12
Nodes (9): AptBackend, Backend, FlatpakBackend, LocalBackend, build_apps(), SnapBackend, WineBackend, App (+1 more)

### Community 19 - "Page Background Work"
Cohesion: 0.12
Nodes (10): work(), log(), DiagnosePage, work(), work(), work(), work(), Dialog (+2 more)

### Community 20 - "Canvas Tags & Text Fit"
Cohesion: 0.13
Nodes (3): draw_tag(), fit_text(), Table

### Community 21 - "Uninstall Table Filtering"
Cohesion: 0.15
Nodes (4): format_size(), UninstallPage, work(), work()

### Community 22 - "Linux Vitals Sensors"
Cohesion: 0.13
Nodes (16): chip_label(), drive_health(), group_temps(), _milli(), parse_drives(), parse_meminfo(), Partition, _read() (+8 more)

### Community 23 - "Windows GUI Shell & Theme"
Cohesion: 0.14
Nodes (5): resized(), ActionBar, Button, px(), Rounded

### Community 24 - "Windows Cleanup Engine"
Cohesion: 0.17
Nodes (14): browser_caches(), _children(), clean(), is_stale(), Location, _one(), _recycle_bin_size(), scan() (+6 more)

### Community 26 - "Android App Scanner"
Cohesion: 0.13
Nodes (4): Scanner, SizeReader, installerLabelFor(), sourceFor()

### Community 27 - "Linux Flatpak Backend"
Cohesion: 0.20
Nodes (7): build_apps(), Risk, Source, classify_default(), classify_local(), classify_runtime_name(), test_snap_list_parse_and_runtime_detection()

### Community 28 - "Windows Registry Backend"
Cohesion: 0.12
Nodes (14): build_apps(), is_listable(), read_uninstall_entries(), _read_view(), RegistryBackend, registered(), uninstall_command_line(), _value() (+6 more)

### Community 29 - "Windows Self-Update & Launch"
Cohesion: 0.12
Nodes (12): main(), install(), install_kind(), is_newer(), _kind(), latest(), parse_version(), pick_asset() (+4 more)

### Community 30 - "Flatpak List Parsing"
Cohesion: 0.10
Nodes (4): parse_flatpak_list(), _elf_with_update_info(), test_appimage_update_info(), test_flatpak_parse()

### Community 31 - "Page Done Callbacks"
Cohesion: 0.12
Nodes (5): DiagnosePage, _follow(), run(), confirm(), strong()

### Community 32 - "Windows Icon Dock"
Cohesion: 0.15
Nodes (3): ico_pictures(), _system_theme(), UninstallerWindow

### Community 33 - "Linux Feature Decisions"
Cohesion: 0.10
Nodes (6): Stitches (Linux 0.2), Features, Planned: fragmentation analysis before defrag, Done: Stitches 0.2 fifth round, Done: Stitches 0.2 (first round / rename), Done: Stitches 0.2 third round

### Community 34 - "Linux Action Bar & Toast"
Cohesion: 0.14
Nodes (3): ActionBar, tick(), worker()

### Community 36 - "Windows Defrag Page"
Cohesion: 0.19
Nodes (3): DefragPage, Tick, Tooltip

### Community 37 - "Android Uninstall Flow"
Cohesion: 0.25
Nodes (3): formatSize(), RemovalResult, UninstallPage

### Community 38 - "Linux Self-Update"
Cohesion: 0.14
Nodes (9): install(), install_kind(), is_newer(), latest(), parse_version(), pick_asset(), restart(), download() (+1 more)

### Community 39 - "Chocolatey & Scoop Backends"
Cohesion: 0.19
Nodes (4): build_apps(), build_apps(), Source, classify_managed_package()

### Community 40 - "Android Permissions"
Cohesion: 0.17
Nodes (6): allFilesAccessIntent(), hasUsageAccess(), usageAccessIntent(), leftoversFor(), removalIntent(), removalOutcome()

### Community 41 - "Linux Cleanup Page"
Cohesion: 0.17
Nodes (3): CleanupPage, work(), _pretty()

### Community 42 - "Linux System Info"
Cohesion: 0.18
Nodes (11): describe_firmware(), disk_label(), _disks(), parse_cpuinfo(), parse_meminfo(), parse_os_release(), pick_board(), _read() (+3 more)

### Community 43 - "Android Risk Classifier"
Cohesion: 0.24
Nodes (4): classify(), RiskSignals, RiskVerdict, CoreTest

### Community 44 - "Progress Bar Animation"
Cohesion: 0.18
Nodes (4): tick(), tick(), tick(), worker()

### Community 45 - "Android Port Decisions"
Cohesion: 0.14
Nodes (6): Android port (android/), Themes: Light, Dark, AMOLED, Glass, Windows port (windows/), Done: Android feature checklist, Planned: Play-flavoured Android build, Done: Windows feature checklist

### Community 47 - "Android Leftover Scan"
Cohesion: 0.19
Nodes (6): deletePaths(), findLeftovers(), pathSize(), scanRoots(), searchTerms(), cleanLeftovers()

### Community 48 - "Windows Leftover Scan"
Cohesion: 0.21
Nodes (6): find_leftovers(), scan_roots(), backend_for(), clean_leftovers(), uninstall(), test_leftovers_name_match()

### Community 49 - "Android Data Models"
Cohesion: 0.18
Nodes (11): App, Risk, CAUTION, CRITICAL, SAFE, Source, FDROID, OTHER_STORE (+3 more)

### Community 50 - "Linux Defrag Engine"
Cohesion: 0.23
Nodes (7): defrag(), Drive, find_drives(), os_of(), parse_lsblk(), walk(), plan()

### Community 51 - "APT Parsing & Risk"
Cohesion: 0.21
Nodes (7): build_apps(), parse_dpkg_query(), parse_showmanual(), classify_apt(), test_classify_apt(), test_dpkg_query_parse(), test_showmanual_and_build_apps()

### Community 56 - "Cross-Platform Safety Principles"
Cohesion: 0.20
Nodes (4): Done: Linux v0.1 feature checklist, Planned: reverse-dependency check for apt packages, Non-functional Requirements, Risk classification: Safe/Caution/Critical

### Community 57 - "Windows Port Decisions"
Cohesion: 0.20
Nodes (3): Windows: the Stitches design and tools (0.2.0), Planned: bring Android build the new tools, Done: Windows Stitches design and tools (0.2.0)

### Community 58 - "Linux Uninstall & Leftovers"
Cohesion: 0.27
Nodes (5): find_leftovers(), backend_for(), clean_leftovers(), uninstall(), test_leftovers_name_match()

### Community 59 - "Android Health & Icon Decisions"
Cohesion: 0.22
Nodes (3): The Stitches design (Android), Done: Android Stitches design, Done: Stitches 0.2 second round

### Community 60 - "Android Leftover Decisions"
Cohesion: 0.22
Nodes (5): Planned: split Android leftover scan by confidence, Planned: package-manager-owned leftovers under /etc, Planned: per-app Program Files leftovers, Planned: registry leftovers (orphaned HKCU keys), Functional Requirements FR1-FR9

### Community 61 - "Wine Backend"
Cohesion: 0.25
Nodes (5): build_apps(), find_prefixes(), parse_uninstall_keys(), _unescape(), test_wine_uninstall_key_parse()

### Community 62 - "GitHub/AppImage Updates"
Cohesion: 0.22
Nodes (5): _github_updates(), parse_update_info(), pick_asset(), read_update_info(), version_label()

### Community 64 - "Canvas Stroke Primitives"
Cohesion: 0.25
Nodes (6): _box(), _line(), inside(), _triangle(), inside(), side()

### Community 65 - "Scoop Manifest Parsing"
Cohesion: 0.29
Nodes (4): install_roots(), parse_manifest(), read_packages(), test_scoop_manifest_and_directory_scan()

### Community 66 - "Chocolatey Nuspec Parsing"
Cohesion: 0.33
Nodes (4): install_root(), parse_nuspec(), read_packages(), test_nuspec_parse_and_manager_is_critical()

### Community 67 - "Local Install Backend"
Cohesion: 0.40
Nodes (3): install_paths(), _version(), test_local_install_and_driver_purpose()

### Community 70 - "App Icon & Mockup"
Cohesion: 0.50
Nodes (5): Linux Uninstaller Main Window Mockup, Stitches Linux App Icon (Stitched Hourglass), Stitches Uninstall Action Symbolic Icon, Tool Brush Symbolic Icon, Stitches Windows Uninstaller App Icon (Hourglass)

### Community 72 - "Diagnostics Symbolic Icons"
Cohesion: 0.50
Nodes (4): CPU Symbolic Icon, Device Diagnostics Symbolic Icon, Memory (RAM) Symbolic Icon, Temperature Sensor Symbolic Icon

## Ambiguous Edges - Review These
- `Windows: the Stitches design and tools (0.2.0)` → `Planned: bring Android build the new tools`  [AMBIGUOUS]
  documents/features.md · relation: references
- `Linux Uninstaller Main Window Mockup` → `Tool Brush Symbolic Icon`  [AMBIGUOUS]
  linux/src/stitches/icons/tool-brush-symbolic.svg · relation: conceptually_related_to

## Knowledge Gaps
- **83 isolated node(s):** `OK`, `WARNING`, `PROBLEM`, `INFO`, `PLAY` (+78 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 589 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **85 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `Windows: the Stitches design and tools (0.2.0)` and `Planned: bring Android build the new tools`?**
  _Edge tagged AMBIGUOUS (relation: references) - confidence is low._
- **What is the exact relationship between `Linux Uninstaller Main Window Mockup` and `Tool Brush Symbolic Icon`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `UpdatesPage` connect `Windows Updates Table` to `Linux Page Widgets`, `Linux App Package`, `Linux GTK Main Window`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `px()` connect `Windows GUI Shell & Theme` to `Windows Icon Dock`, `Windows App Entry & Pages`, `Windows Defrag Page`, `Windows Tk Widgets`, `Windows Uninstall Select-All`, `Progress Bar Animation`, `Windows Home Page`, `Page Background Work`, `Canvas Tags & Text Fit`, `Windows Icon Button`, `Filter Pills`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `UninstallPage` (e.g. with `UninstallerWindow` and `Risk`) actually correct?**
  _`UninstallPage` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `App` (e.g. with `AptBackend` and `Backend`) actually correct?**
  _`App` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `App` (e.g. with `Backend` and `ChocoBackend`) actually correct?**
  _`App` has 8 INFERRED edges - model-reasoned connections that need verification._