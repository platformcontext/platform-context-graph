<?php
namespace Comprehensive;

class Service {
    public function info(string $message): void {}
}

class Logger {
    public static function warn(string $message): void {}
}

class Factory {
    public static function instance(): Factory {
        return new Factory();
    }

    public function createService(): Service {
        return new Service();
    }
}

class Config {
    public function run(): void {
        Logger::warn('warn');
    }
}

class Child extends Factory {
    public function run(): void {
        parent::instance()->createService()->info('ready');
    }
}
