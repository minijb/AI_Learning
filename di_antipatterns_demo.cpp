#include <iostream>
#include <memory>
#include <string>
#include <stdexcept>
#include <unordered_map>

// ==================== 核心接口与实现 ====================
class IWeapon {
public:
    virtual ~IWeapon() = default;
    virtual int damage() const = 0;
    virtual std::string name() const = 0;
};

class Sword : public IWeapon {
public:
    int damage() const override { return 15; }
    std::string name() const override { return "铁剑"; }
};

class ILogger {
public:
    virtual ~ILogger() = default;
    virtual void log(const std::string& msg) = 0;
};

class ConsoleLogger : public ILogger {
public:
    void log(const std::string& msg) override {
        std::cout << "[log] " << msg << "\n";
    }
};

// ==================== Service Locator 反模式 ====================
class ServiceLocator {
public:
    template<typename T>
    static T& Get() {
        auto it = instance().services_.find(typeid(T).name());
        if (it == instance().services_.end()) {
            throw std::runtime_error("Service not registered");
        }
        return *static_cast<T*>(it->second);
    }

    template<typename T, typename Impl>
    static void Register() {
        instance().services_[typeid(T).name()] = std::make_unique<Impl>().release();
    }

    static void Reset() {
        instance().services_.clear();
    }

private:
    static ServiceLocator& instance() {
        static ServiceLocator loc;
        return loc;
    }
    std::unordered_map<std::string, void*> services_;
    ~ServiceLocator() {
        for (auto& [k, v] : services_) delete static_cast<char*>(v);
    }
};

class ServiceLocatorHero {
public:
    void attack() {
        auto& weapon = ServiceLocator::Get<IWeapon>();
        auto& logger = ServiceLocator::Get<ILogger>();
        logger.log(weapon.name() + " 造成 " + std::to_string(weapon.damage()) + " 点伤害");
    }
};

// ==================== 构造器注入（正确做法） ====================
class ConstructorInjectedHero {
public:
    ConstructorInjectedHero(IWeapon& weapon, ILogger& logger)
        : weapon_(weapon), logger_(logger) {}

    void attack() {
        logger_.log(weapon_.name() + " 造成 " + std::to_string(weapon_.damage()) + " 点伤害");
    }
private:
    IWeapon& weapon_;
    ILogger& logger_;
};

// ==================== 测试替身 ====================
class MockWeapon : public IWeapon {
public:
    int damage() const override { return 999; }
    std::string name() const override { return "测试之剑"; }
};

class MockLogger : public ILogger {
public:
    std::string lastMsg;
    void log(const std::string& msg) override { lastMsg = msg; }
};

// ==================== 测试 ====================
void testServiceLocatorHero() {
    std::cout << "\n--- Service Locator Hero 测试 ---\n";
    ServiceLocator::Reset();
    ServiceLocator::Register<IWeapon, Sword>();
    ServiceLocator::Register<ILogger, ConsoleLogger>();

    ServiceLocatorHero hero;
    hero.attack();
}

void testConstructorInjectedHero() {
    std::cout << "\n--- 构造器注入 Hero 测试 ---\n";
    MockWeapon weapon;
    MockLogger logger;
    ConstructorInjectedHero hero(weapon, logger);
    hero.attack();
    std::cout << "捕获日志: " << logger.lastMsg << "\n";
}

int main() {
    testServiceLocatorHero();
    testConstructorInjectedHero();
    return 0;
}
