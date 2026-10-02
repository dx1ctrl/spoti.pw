// SPDX-License-Identifier: GPL-3.0-or-later
// Notification delivery for visual controls, kept independent of UIKit so the
// background-posting behavior can be verified by a standalone Foundation test.
import Foundation

@discardableResult
func addAsyncMainObserver(
    center: NotificationCenter = .default,
    name: Notification.Name,
    handler: @escaping (Notification) -> Void
) -> NSObjectProtocol {
    // Observe on the posting thread, then enqueue UI work without waiting for it.
    // A supplied OperationQueue.main can make a background notification wait for
    // main while its sender still holds a lock the UI needs. Even main-thread
    // posts are deferred here, preventing a handler from reentering its caller.
    center.addObserver(forName: name, object: nil, queue: nil) { notification in
        DispatchQueue.main.async {
            handler(notification)
        }
    }
}
