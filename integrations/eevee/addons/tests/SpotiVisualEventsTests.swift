// SPDX-License-Identifier: GPL-3.0-or-later
// Standalone Foundation regression tests. Compile with SpotiVisualEvents.swift.
import Foundation

@main
struct SpotiVisualEventsTests {
    static var checks = 0

    static func check(_ condition: @autoclosure () -> Bool, _ message: String) {
        checks += 1
        precondition(condition(), message)
    }

    static func drainMain(until condition: () -> Bool) {
        let deadline = Date().addingTimeInterval(3)
        while !condition() && Date() < deadline {
            _ = RunLoop.main.run(mode: .default, before: Date().addingTimeInterval(0.01))
        }
        check(condition(), "Notification delivery must complete when the main run loop resumes")
    }

    static func main() {
        check(Thread.isMainThread, "The test must start on the main thread")
        let center = NotificationCenter()
        let name = Notification.Name("SpotiVisualEventsTests.delivery")
        let background = DispatchQueue(label: "SpotiVisualEventsTests.sender")
        let posted = DispatchSemaphore(value: 0)
        var delivered: [Int] = []
        var mainThreadDeliveries: [Bool] = []
        var insideHandler = false
        var reentered = false

        let observer = addAsyncMainObserver(center: center, name: name) { notification in
            mainThreadDeliveries.append(Thread.isMainThread)
            reentered = reentered || insideHandler
            insideHandler = true
            defer { insideHandler = false }
            let sequence = notification.userInfo!["sequence"] as! Int
            delivered.append(sequence)
            if sequence == 5 {
                // Posting a second event while handling the first must enqueue
                // its delivery, rather than recursively enter this handler.
                center.post(name: name, object: nil, userInfo: ["sequence": 6])
                check(delivered.last == 5, "Nested posts must not reenter the active handler")
            }
        }
        defer { center.removeObserver(observer) }

        background.async {
            center.post(name: name, object: nil, userInfo: ["sequence": 1])
            posted.signal()
        }
        // Main deliberately does not service its queue here. A synchronous hop
        // from NotificationCenter to OperationQueue.main would block the sender
        // and fail this bounded wait, reproducing the startup-hang hazard.
        check(posted.wait(timeout: .now() + 3) == .success,
              "Background notification posting must finish while the main thread is blocked")
        check(delivered.isEmpty, "Background posts must not run handlers inline")
        drainMain { delivered.count == 1 }
        check(delivered == [1], "The first event must arrive exactly once")

        background.async {
            for sequence in 2...4 {
                center.post(name: name, object: nil, userInfo: ["sequence": sequence])
            }
            posted.signal()
        }
        check(posted.wait(timeout: .now() + 3) == .success,
              "A burst of background notifications must not wait for main")
        check(delivered == [1], "Burst delivery must remain deferred until main resumes")
        drainMain { delivered.count == 4 }
        check(delivered == [1, 2, 3, 4], "Events from one posting queue must retain their order")

        center.post(name: name, object: nil, userInfo: ["sequence": 5])
        check(delivered == [1, 2, 3, 4], "Main-thread posts must also defer their handlers")
        drainMain { delivered.count == 6 }
        check(delivered == [1, 2, 3, 4, 5, 6], "Nested events must arrive once and after their parent")
        check(!reentered, "Notification handlers must never be synchronously reentered")
        check(mainThreadDeliveries.count == 6 && mainThreadDeliveries.allSatisfy { $0 },
              "Every handler must run on the main thread")
        print("SpotiVisualEvents: \(checks) checks passed")
    }
}
