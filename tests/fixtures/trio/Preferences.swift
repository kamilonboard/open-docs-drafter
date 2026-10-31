import Foundation

struct Preferences: JSON, Equatable {
    var maxIOB: Decimal = 0
    var maxSMBBasalMinutes: Decimal = 30 // minutes of basal
    var enableSMBAlways: Bool = false
    var curve: InsulinCurve = .rapidActing
    var smbInterval: Decimal = 3
    var computedLimit: Decimal = maxIOB * 2
    var timestamp: Date?
}

extension Preferences {
    private enum CodingKeys: String, CodingKey {
        case maxIOB = "max_iob"
        case maxSMBBasalMinutes
        case enableSMBAlways = "enableSMB_always"
        case curve
        case smbInterval = "SMBInterval"
        case computedLimit, timestamp
    }
}
