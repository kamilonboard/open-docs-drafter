import SwiftUI

struct UnitsLimitsSettingsRootView: View {
    var body: some View {
        List {
            SettingInputSection(
                decimalValue: $state.maxBasal,
                booleanValue: $booleanPlaceholder,
                units: state.units,
                type: .decimal("maxBasal"),
                label: String(localized: "Maximum Basal Rate"),
                verboseHint:
                VStack(alignment: .leading, spacing: 10) {
                    Text("Default: 2 \(String(localized: "U/hr", comment: "Insulin unit per hour abbreviation"))").bold()
                }
            )

            SettingInputSection(
                decimalValue: $state.maxDailySafetyMultiplier,
                booleanValue: $booleanPlaceholder,
                units: state.units,
                type: .decimal("maxDailySafetyMultiplier"),
                label: String(localized: "Max Daily Safety Multiplier"),
                verboseHint: VStack {
                    Text("Default: 300%").bold()
                }
            )

            SettingInputSection(
                decimalValue: $state.halfBasalExerciseTarget,
                booleanValue: $booleanPlaceholder,
                units: state.units,
                type: .decimal("halfBasalExerciseTarget"),
                label: String(localized: "Half Basal Exercise Target"),
                verboseHint: VStack {
                    Text(
                        "Default: \(state.units == .mgdL ? "160" : 160.formattedAsMmolL) \(state.units.rawValue)"
                    ).bold()
                }
            )
        }
    }
}
