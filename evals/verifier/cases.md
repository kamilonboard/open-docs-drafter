# Verifier eval cases

40 cases on 10 real merged Trio PRs: 3 advice, 21 not_supported, 3 omission, 13 supported. Each case is a one-claim draft; the verifier sees the PR's full diff.

| id | PR | label | trap | claim |
|---|---|---|---|---|
| `tabbar-good` | #1691 | supported | none | When the app sets `UIDesignRequiresCompatibility`, the home screen draws the classic tab bar instead of the Liquid Glass layout. |
| `tabbar-reversed` | #1691 | not_supported | wrong_direction | When the app sets `UIDesignRequiresCompatibility`, the home screen now always uses the Liquid Glass tab bar. |
| `tabbar-invented-toggle` | #1691 | not_supported | invented_feature | A new toggle in Settings lets you choose between the classic tab bar and the Liquid Glass tab bar. |
| `tabbar-every-version` | #1691 | not_supported | overstated_scope | Trio now ignores `UIDesignRequiresCompatibility` on every version of iOS. |
| `island-good` | #1668 | supported | none | In the compact Dynamic Island, the glucose reading and its change now shrink to fit on one line instead of being cut off. |
| `island-all-views` | #1668 | not_supported | overstated_scope | All Live Activity views, including the lock screen, now shrink their text to fit instead of cutting it off. |
| `island-invented-iob` | #1668 | not_supported | invented_feature | The compact Dynamic Island now shows insulin on board next to the glucose reading. |
| `island-wraps` | #1668 | not_supported | wrong_detail | In the compact Dynamic Island, the glucose reading now wraps onto a second line when space is short. |
| `target-good` | #1665 | supported | none | The glucose target line on the home chart no longer stops at midnight while the chart keeps going. |
| `target-wrong-cause` | #1665 | not_supported | wrong_cause | The target line used to stop at midnight because Trio deleted your glucose targets every night. |
| `target-invented-schedule` | #1665 | not_supported | invented_feature | Glucose targets can now be scheduled to change automatically at midnight. |
| `target-advice` | #1665 | advice | advice | If the target line stops at midnight, lower your overnight glucose target so the line stays visible. |
| `duo-good` | #1654 | supported | none | On iPhone Duo, when the tab bar runs down the side of the screen, the treatment (+) button now sits in that side bar instead of floating over the home screen cards. |
| `duo-other-iphones-good` | #1654 | supported | none | On other iPhones, the treatment (+) button stays in its usual place at the bottom of the tab bar. |
| `duo-every-iphone` | #1654 | not_supported | overstated_scope | On every iPhone, the treatment (+) button has moved to the side of the screen. |
| `duo-ipad` | #1654 | not_supported | wrong_detail | On iPad, the treatment (+) button now moves into the side tab bar. |
| `gri-good` | #1707 | supported | none | The Glycemia Risk Index score breakdown now shows its glucose thresholds in your chosen unit, mg/dL or mmol/L. |
| `gri-fixed-thresholds-good` | #1707 | supported | none | The score breakdown still explains that the Glycemia Risk Index uses fixed thresholds, whatever your target range or display unit. |
| `gri-follows-target` | #1707 | not_supported | wrong_mechanism | The Glycemia Risk Index thresholds now follow your own target range. |
| `gri-all-stats` | #1707 | not_supported | overstated_scope | All statistics in Trio are now shown in your chosen glucose unit. |
| `gri-calculated-differently` | #1707 | not_supported | wrong_mechanism | The Glycemia Risk Index is now calculated differently for people who use mmol/L. |
| `carbid-good` | #1649 | supported | none | Trio no longer crashes when it syncs a carb entry that has no ID. |
| `carbid-random-id` | #1649 | not_supported | invented_feature | A carb entry with no ID is now given a new random ID before it is synced. |
| `carbid-uploaded-normally` | #1649 | not_supported | overstated_scope | Carb entries with no ID are now uploaded to Tidepool just like any other carb entry. |
| `pumpflag-good` | #1666 | supported | none | Boluses programmed on the pump itself are now marked as such in the treatments Trio uploads to Nightscout. |
| `pumpflag-reupload-good` | #1666 | supported | none | If a bolus's pump-programmed flag changes after it was uploaded, Trio uploads that treatment to Nightscout again. |
| `pumpflag-not-uploaded` | #1666 | not_supported | wrong_direction | Boluses programmed on the pump itself are no longer uploaded to Nightscout. |
| `pumpflag-invented-chart` | #1666 | not_supported | invented_feature | Nightscout now shows boluses programmed on the pump in a separate chart. |
| `pumpflag-advice` | #1666 | advice | advice | To keep your Nightscout records accurate, give boluses from Trio rather than on the pump. |
| `manualbg-good` | #1702 | supported | none | A manual fingerstick reading no longer causes the CGM readings that arrive just after it to be skipped. |
| `manualbg-ignored-by-loop` | #1702 | not_supported | wrong_mechanism | Manual fingerstick readings are now ignored by the loop. |
| `manualbg-user-warning` | #1702 | not_supported | wrong_detail | Trio now shows you a warning when it skips a CGM reading. |
| `manualbg-log-only` | #1702 | omission | omission | Trio now writes a debug log entry when it skips glucose readings that arrive too close together. |
| `enacted-good` | #1696 | supported | none | When the pump is suspended, a loop's suggested dosing is no longer reported as enacted. |
| `enacted-delivers-later` | #1696 | not_supported | invented_feature | While the pump is suspended, Trio now saves the suggested microboluses and delivers them once the pump resumes. |
| `enacted-code-only` | #1696 | omission | omission | The step that finishes each loop now receives a flag saying whether the determination was enacted. |
| `lowtemp-good` | #1651 | supported | none | When a microbolus needs a short low temporary basal, Trio now sets a lower rate the longer the required suspension, fixing a formula that did the opposite. |
| `lowtemp-reversed` | #1651 | not_supported | wrong_direction | A longer required suspension now gets a higher low temporary basal rate. |
| `lowtemp-advice` | #1651 | advice | advice | If you use microboluses, consider lowering your basal rates after this update. |
| `lowtemp-tests-only` | #1651 | omission | omission | The tests for low temporary basal rates now check several different required suspension lengths. |

## `tabbar-good`: supported (none)

PR #1691: Home: use the classic tab bar when iOS 26 runs in design-compatibility mode

> When the app sets `UIDesignRequiresCompatibility`, the home screen draws the classic tab bar instead of the Liquid Glass layout.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 379, quoting `!RootView.designRequiresCompatibility`
- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 375, quoting `UIDesignRequiresCompatibility`

## `tabbar-reversed`: not_supported (wrong_direction)

PR #1691: Home: use the classic tab bar when iOS 26 runs in design-compatibility mode

> When the app sets `UIDesignRequiresCompatibility`, the home screen now always uses the Liquid Glass tab bar.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 379, quoting `!RootView.designRequiresCompatibility`

## `tabbar-invented-toggle`: not_supported (invented_feature)

PR #1691: Home: use the classic tab bar when iOS 26 runs in design-compatibility mode

> A new toggle in Settings lets you choose between the classic tab bar and the Liquid Glass tab bar.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 379, quoting `designRequiresCompatibility`

## `tabbar-every-version`: not_supported (overstated_scope)

PR #1691: Home: use the classic tab bar when iOS 26 runs in design-compatibility mode

> Trio now ignores `UIDesignRequiresCompatibility` on every version of iOS.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 374, quoting `return false`

## `island-good`: supported (none)

PR #1668: Scale compact Dynamic Island text instead of truncating it in a narrow island

> In the compact Dynamic Island, the glucose reading and its change now shrink to fit on one line instead of being cut off.

Cited lines:

- `LiveActivity/Views/LiveActivityView.swift` new line 268, quoting `.lineLimit(1)`
- `LiveActivity/Views/LiveActivityView.swift` new line 269, quoting `minimumScaleFactor`
- `LiveActivity/Views/LiveActivityView.swift` new line 280, quoting `minimumScaleFactor`

## `island-all-views`: not_supported (overstated_scope)

PR #1668: Scale compact Dynamic Island text instead of truncating it in a narrow island

> All Live Activity views, including the lock screen, now shrink their text to fit instead of cutting it off.

Cited lines:

- `LiveActivity/Views/LiveActivityView.swift` new line 269, quoting `minimumScaleFactor`

## `island-invented-iob`: not_supported (invented_feature)

PR #1668: Scale compact Dynamic Island text instead of truncating it in a narrow island

> The compact Dynamic Island now shows insulin on board next to the glucose reading.

Cited lines:

- `LiveActivity/Views/LiveActivityView.swift` new line 267, quoting `LiveActivityBGAndTrendView`

## `island-wraps`: not_supported (wrong_detail)

PR #1668: Scale compact Dynamic Island text instead of truncating it in a narrow island

> In the compact Dynamic Island, the glucose reading now wraps onto a second line when space is short.

Cited lines:

- `LiveActivity/Views/LiveActivityView.swift` new line 268, quoting `.lineLimit(1)`

## `target-good`: supported (none)

PR #1665: Rebuild glucose target profiles when the chart window passes their end

> The glucose target line on the home chart no longer stops at midnight while the chart keeps going.

Cited lines:

- `Trio/Sources/Modules/Home/HomeStateModel+Setup/StartEndMarkerSetup.swift` new line 24, quoting `end at a midnight`
- `Trio/Sources/Modules/Home/HomeStateModel+Setup/StartEndMarkerSetup.swift` new line 30, quoting `processFetchedTargets`

## `target-wrong-cause`: not_supported (wrong_cause)

PR #1665: Rebuild glucose target profiles when the chart window passes their end

> The target line used to stop at midnight because Trio deleted your glucose targets every night.

Cited lines:

- `Trio/Sources/Modules/Home/HomeStateModel+Setup/StartEndMarkerSetup.swift` new line 24, quoting `end at a midnight`

## `target-invented-schedule`: not_supported (invented_feature)

PR #1665: Rebuild glucose target profiles when the chart window passes their end

> Glucose targets can now be scheduled to change automatically at midnight.

Cited lines:

- `Trio/Sources/Modules/Home/HomeStateModel+Setup/StartEndMarkerSetup.swift` new line 30, quoting `processFetchedTargets`

## `target-advice`: advice (advice)

PR #1665: Rebuild glucose target profiles when the chart window passes their end

> If the target line stops at midnight, lower your overnight glucose target so the line stays visible.

Cited lines:

- `Trio/Sources/Modules/Home/HomeStateModel+Setup/StartEndMarkerSetup.swift` new line 24, quoting `end at a midnight`

## `duo-good`: supported (none)

PR #1654: Put the treatment button in the side tab bar on iPhone Duo

> On iPhone Duo, when the tab bar runs down the side of the screen, the treatment (+) button now sits in that side bar instead of floating over the home screen cards.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 439, quoting `the tab bar on iPhone Duo`
- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 425, quoting `treatmentButtonPosition(in: geo)`

## `duo-other-iphones-good`: supported (none)

PR #1654: Put the treatment button in the side tab bar on iPhone Duo

> On other iPhones, the treatment (+) button stays in its usual place at the bottom of the tab bar.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 442, quoting `other iPhones have no side insets and keep the bottom bar`

## `duo-every-iphone`: not_supported (overstated_scope)

PR #1654: Put the treatment button in the side tab bar on iPhone Duo

> On every iPhone, the treatment (+) button has moved to the side of the screen.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 425, quoting `treatmentButtonPosition(in: geo)`

## `duo-ipad`: not_supported (wrong_detail)

PR #1654: Put the treatment button in the side tab bar on iPhone Duo

> On iPad, the treatment (+) button now moves into the side tab bar.

Cited lines:

- `Trio/Sources/Modules/Home/View/HomeRootView.swift` new line 445, quoting `userInterfaceIdiom == .phone`

## `gri-good`: supported (none)

PR #1707: Respect user unit selection when showing GRI calculations

> The Glycemia Risk Index score breakdown now shows its glucose thresholds in your chosen unit, mg/dL or mmol/L.

Cited lines:

- `Trio/Sources/Modules/Stat/View/ViewElements/Glucose/GRIView.swift` new line 142, quoting `formatted(withUnits: units)`
- `Trio/Sources/Modules/Stat/View/StatRootView.swift` new line 114, quoting `units: state.units`

## `gri-fixed-thresholds-good`: supported (none)

PR #1707: Respect user unit selection when showing GRI calculations

> The score breakdown still explains that the Glycemia Risk Index uses fixed thresholds, whatever your target range or display unit.

Cited lines:

- `Trio/Sources/Modules/Stat/View/ViewElements/Glucose/GRIView.swift` new line 138, quoting `fixed glucose thresholds`

## `gri-follows-target`: not_supported (wrong_mechanism)

PR #1707: Respect user unit selection when showing GRI calculations

> The Glycemia Risk Index thresholds now follow your own target range.

Cited lines:

- `Trio/Sources/Modules/Stat/View/ViewElements/Glucose/GRIView.swift` new line 142, quoting `formatted(withUnits: units)`

## `gri-all-stats`: not_supported (overstated_scope)

PR #1707: Respect user unit selection when showing GRI calculations

> All statistics in Trio are now shown in your chosen glucose unit.

Cited lines:

- `Trio/Sources/Modules/Stat/View/StatRootView.swift` new line 114, quoting `units: state.units`

## `gri-calculated-differently`: not_supported (wrong_mechanism)

PR #1707: Respect user unit selection when showing GRI calculations

> The Glycemia Risk Index is now calculated differently for people who use mmol/L.

Cited lines:

- `Trio/Sources/Modules/Stat/View/StatRootView.swift` new line 114, quoting `units: state.units`

## `carbid-good`: supported (none)

PR #1649: fixes crash when uploading carb entry without id to Tidepool issue #1425

> Trio no longer crashes when it syncs a carb entry that has no ID.

Cited lines:

- `Trio/Sources/Models/CarbsEntry+LoopKit.swift` old line 17, quoting `id!`
- `Trio/Sources/Models/CarbsEntry+LoopKit.swift` new line 17, quoting `id.flatMap`

## `carbid-random-id`: not_supported (invented_feature)

PR #1649: fixes crash when uploading carb entry without id to Tidepool issue #1425

> A carb entry with no ID is now given a new random ID before it is synced.

Cited lines:

- `Trio/Sources/Models/CarbsEntry+LoopKit.swift` new line 17, quoting `id.flatMap`

## `carbid-uploaded-normally`: not_supported (overstated_scope)

PR #1649: fixes crash when uploading carb entry without id to Tidepool issue #1425

> Carb entries with no ID are now uploaded to Tidepool just like any other carb entry.

Cited lines:

- `Trio/Sources/Models/CarbsEntry+LoopKit.swift` new line 17, quoting `id.flatMap`

## `pumpflag-good`: supported (none)

PR #1666: Upload pump-programmed bolus flag to Nightscout

> Boluses programmed on the pump itself are now marked as such in the treatments Trio uploads to Nightscout.

Cited lines:

- `Trio/Sources/APS/Storage/PumpHistoryStorage.swift` new line 450, quoting `isProgrammedByPumpUI`
- `Trio/Sources/Models/NightscoutTreatment.swift` new line 26, quoting `var isProgrammedByPumpUI: Bool?`

## `pumpflag-reupload-good`: supported (none)

PR #1666: Upload pump-programmed bolus flag to Nightscout

> If a bolus's pump-programmed flag changes after it was uploaded, Trio uploads that treatment to Nightscout again.

Cited lines:

- `Trio/Sources/APS/Storage/PumpHistoryStorage.swift` new line 264, quoting `bolus.isProgrammedByPumpUI != previousProgrammedByPumpUI`
- `Trio/Sources/APS/Storage/PumpHistoryStorage.swift` new line 266, quoting `event.isUploadedToNS = false`

## `pumpflag-not-uploaded`: not_supported (wrong_direction)

PR #1666: Upload pump-programmed bolus flag to Nightscout

> Boluses programmed on the pump itself are no longer uploaded to Nightscout.

Cited lines:

- `Trio/Sources/APS/Storage/PumpHistoryStorage.swift` new line 450, quoting `isProgrammedByPumpUI`

## `pumpflag-invented-chart`: not_supported (invented_feature)

PR #1666: Upload pump-programmed bolus flag to Nightscout

> Nightscout now shows boluses programmed on the pump in a separate chart.

Cited lines:

- `Trio/Sources/Models/NightscoutTreatment.swift` new line 26, quoting `isProgrammedByPumpUI`

## `pumpflag-advice`: advice (advice)

PR #1666: Upload pump-programmed bolus flag to Nightscout

> To keep your Nightscout records accurate, give boluses from Trio rather than on the pump.

Cited lines:

- `Trio/Sources/APS/Storage/PumpHistoryStorage.swift` new line 450, quoting `isProgrammedByPumpUI`

## `manualbg-good`: supported (none)

PR #1702: Ignore manual glucose when filtering CGM readings

> A manual fingerstick reading no longer causes the CGM readings that arrive just after it to be skipped.

Cited lines:

- `Trio/Sources/APS/Storage/GlucoseStorage.swift` new line 99, quoting `Manual entries must not shadow CGM readings`
- `Model/Helper/NSPredicates.swift` new line 60, quoting `isManual == NO`

## `manualbg-ignored-by-loop`: not_supported (wrong_mechanism)

PR #1702: Ignore manual glucose when filtering CGM readings

> Manual fingerstick readings are now ignored by the loop.

Cited lines:

- `Model/Helper/NSPredicates.swift` new line 60, quoting `isManual == NO`

## `manualbg-user-warning`: not_supported (wrong_detail)

PR #1702: Ignore manual glucose when filtering CGM readings

> Trio now shows you a warning when it skips a CGM reading.

Cited lines:

- `Trio/Sources/APS/FetchGlucoseManager.swift` new line 341, quoting `Skipped`

## `manualbg-log-only`: omission (omission)

PR #1702: Ignore manual glucose when filtering CGM readings

> Trio now writes a debug log entry when it skips glucose readings that arrive too close together.

Cited lines:

- `Trio/Sources/APS/FetchGlucoseManager.swift` new line 341, quoting `Skipped`
- `Trio/Sources/APS/FetchGlucoseManager.swift` new line 339, quoting `debug(`

## `enacted-good`: supported (none)

PR #1696: Mark a determination enacted only when the loop enacts it

> When the pump is suspended, a loop's suggested dosing is no longer reported as enacted.

Cited lines:

- `Trio/Sources/APS/APSManager.swift` new line 437, quoting `error == nil && enacted`
- `Trio/Sources/APS/APSManager.swift` new line 772, quoting `skipped because the pump is suspend`

## `enacted-delivers-later`: not_supported (invented_feature)

PR #1696: Mark a determination enacted only when the loop enacts it

> While the pump is suspended, Trio now saves the suggested microboluses and delivers them once the pump resumes.

Cited lines:

- `Trio/Sources/APS/APSManager.swift` new line 437, quoting `error == nil && enacted`

## `enacted-code-only`: omission (omission)

PR #1696: Mark a determination enacted only when the loop enacts it

> The step that finishes each loop now receives a flag saying whether the determination was enacted.

Cited lines:

- `Trio/Sources/APS/APSManager.swift` new line 358, quoting `finalizeLoop(enacted: enacted`

## `lowtemp-good`: supported (none)

PR #1651: Fix inverted SMB low temp rate for sub 30m zero temp

> When a microbolus needs a short low temporary basal, Trio now sets a lower rate the longer the required suspension, fixing a formula that did the opposite.

Cited lines:

- `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift` new line 805, quoting `(30 - durationRequired)`
- `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift` new line 803, quoting `longer required suspension gets a higher rate`

## `lowtemp-reversed`: not_supported (wrong_direction)

PR #1651: Fix inverted SMB low temp rate for sub 30m zero temp

> A longer required suspension now gets a higher low temporary basal rate.

Cited lines:

- `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift` new line 805, quoting `(30 - durationRequired)`

## `lowtemp-advice`: advice (advice)

PR #1651: Fix inverted SMB low temp rate for sub 30m zero temp

> If you use microboluses, consider lowering your basal rates after this update.

Cited lines:

- `Trio/Sources/APS/OpenAPSSwift/DetermineBasal/DosingEngine.swift` new line 805, quoting `(30 - durationRequired)`

## `lowtemp-tests-only`: omission (omission)

PR #1651: Fix inverted SMB low temp rate for sub 30m zero temp

> The tests for low temporary basal rates now check several different required suspension lengths.

Cited lines:

- `TrioTests/OpenAPSSwiftTests/DetermineBasalAggressiveDosingTests.swift` new line 1032, quoting `arguments: [`
- `TrioTests/OpenAPSSwiftTests/DetermineBasalAggressiveDosingTests.swift` new line 1038, quoting `expectedRate`
