private static AssertionError catchAssertionError(ThrowingRunnable runnable) {
        try {
            runnable.run();
            return null;
        } catch (AssertionError e) {
            return e;
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }