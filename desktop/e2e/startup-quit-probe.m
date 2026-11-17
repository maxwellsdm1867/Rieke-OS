// Test-only macOS helper. Never selects by bundle ID or sends a forced termination.
#import <AppKit/AppKit.h>
#import <libproc.h>
#import <CoreGraphics/CoreGraphics.h>
#import <unistd.h>

static int fail(NSString *message) {
    fprintf(stderr, "%s\n", message.UTF8String);
    return 1;
}

static NSString *physical(NSString *file) {
    char resolved[PATH_MAX];
    return file && realpath(file.fileSystemRepresentation, resolved) ? [NSString stringWithUTF8String:resolved] : nil;
}

int main(int argc, const char **argv) {
    @autoreleasepool {
        NSArray<NSString *> *args = NSProcessInfo.processInfo.arguments;
        // Exercise the same nested /usr/bin/open invocation as the unsigned front door.
        if (argc == 4 && [args[1] isEqual:@"probe-parent"]) {
            NSTask *task = [NSTask new];
            task.launchPath = @"/usr/bin/open";
            task.arguments = @[@"-n", @"-a", args[2], @"--args", @"probe-child", args[3]];
            NSError *error = nil;
            if (![task launchAndReturnError:&error]) return fail(error.localizedDescription);
            [task waitUntilExit];
            return task.terminationStatus;
        }
        if (argc == 3 && [args[1] isEqual:@"probe-child"]) {
            NSDictionary *env = NSProcessInfo.processInfo.environment;
            NSDictionary *paths = @{@"home": env[@"HOME"] ?: @"", @"cocoa_home": NSHomeDirectory(),
                                    @"temporary": env[@"TMPDIR"] ?: @"", @"preferences":env[@"RIEKE_PREFERENCES_DIR"] ?: @""};
            NSData *data = [NSJSONSerialization dataWithJSONObject:paths options:0 error:nil];
            return [data writeToFile:args[2] atomically:YES] ? 0 : fail(@"Could not save isolation evidence");
        }
        if (argc != 7 || !([args[1] isEqual:@"quit"] || [args[1] isEqual:@"window"]))
            return fail(@"Expected quit PID absolute-bundle registry-or-dash project-id project-path");
        pid_t pid = args[2].intValue;
        NSRunningApplication *app = [NSRunningApplication runningApplicationWithProcessIdentifier:pid];
        NSString *bundle = args[3];
        NSString *expected = [bundle stringByAppendingPathComponent:@"Contents/MacOS/Disco"];
        char executable[PROC_PIDPATHINFO_MAXSIZE] = {};
        if (pid < 2 || !app || ![bundle isAbsolutePath] ||
            ![physical(app.bundleURL.path) isEqual:bundle] ||
            !proc_pidpath(pid, executable, sizeof(executable)) ||
            ![physical([NSString stringWithUTF8String:executable]) isEqual:expected])
            return fail(@"Quit target differs from the exact owned application instance");
        if ([args[1] isEqual:@"window"]) {
            // WindowServer publishes owner PID and bounds without controlling
            // the desktop. Window titles can be redacted by macOS privacy.
            NSArray *windows = CFBridgingRelease(CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID));
            NSMutableArray *titles = [NSMutableArray array];
            for (NSDictionary *window in windows) {
                if ([window[(id)kCGWindowOwnerPID] intValue] != pid || [window[(id)kCGWindowLayer] intValue] != 0) continue;
                NSDictionary *bounds=window[(id)kCGWindowBounds];
                if ([bounds[@"Width"] intValue] < 200 || [bounds[@"Height"] intValue] < 150) continue;
                NSString *title = window[(id)kCGWindowName];
                [titles addObject:title ?: NSNull.null];
            }
            NSDictionary *result = @{@"titles":titles, @"can_read_titles":@(CGPreflightScreenCaptureAccess())};
            NSData *json = [NSJSONSerialization dataWithJSONObject:result options:0 error:nil];
            if (!json) return fail(@"Could not encode owned window observations");
            fwrite(json.bytes, 1, json.length, stdout);
            return 0;
        }
        NSString *phase = @"ready";
        if (![args[4] isEqual:@"-"]) {
            NSTimeInterval deadline = NSProcessInfo.processInfo.systemUptime + 90;
            for (;;) {
                NSData *data = [NSData dataWithContentsOfFile:args[4]];
                NSDictionary *registry = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
                if (data && ![registry[@"services"] isKindOfClass:NSArray.class]) return fail(@"Malformed project registry");
                NSDictionary *service = nil;
                for (NSDictionary *row in registry[@"services"]) {
                    if ([row[@"project_uuid"] isEqual:args[5]] && [row[@"project_path"] isEqual:args[6]]) service = row;
                }
                if (service) {
                    if (![service[@"bound"] isEqual:@NO])
                        return fail(@"Missed startup observation: project listener already bound; no early Quit verdict");
                    break;
                }
                if (NSProcessInfo.processInfo.systemUptime >= deadline)
                    return fail(@"Project was never observed starting; ordinary Quit was not sent");
                usleep(10000);
            }
            phase = @"project-spawned-before-listener-binding";
        }
        // AppKit requests normal Quit from this exact application. It runs the
        // same application termination handlers as an OS Quit event, without
        // an accessibility permission or a keystroke aimed at the frontmost app.
        if (![app terminate]) return fail(@"The application did not accept the ordinary OS Quit request");
        puts(phase.UTF8String);
        return 0;
    }
}
