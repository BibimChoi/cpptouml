#pragma once
#include <string>
#include <vector>

class Animal {
public:
    Animal();
    virtual ~Animal();

    virtual void speak() = 0;
    void setName(const std::string& name);
    std::string getName() const;

protected:
    std::string name;
    int age;
};

class Dog : public Animal {
public:
    Dog();
    void speak() override;
    void fetch();

private:
    std::string breed;
    bool trained;
};

class Cat : public Animal {
public:
    Cat();
    void speak() override;
    void scratch();

private:
    int lives;
};

class Zoo {
public:
    void addAnimal(Animal* animal);
    void showAll();

private:
    std::vector<Animal*> animals;
    std::string zooName;
};
