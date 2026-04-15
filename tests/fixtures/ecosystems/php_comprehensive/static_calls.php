<?php
namespace Comprehensive;

class Logger {
    public static function warn(string $message): void {}
}

class Config {
    public function run(): void {
        Logger::warn('warn');
    }
}
