"""
Module `chatette.units`
Contains the definition of the units (i.e. rules and their contents)
that make up the Abstract Syntax Tree, and the logic associated to
their generation.
"""

from __future__ import print_function
import re
import sys
from random import randint
from copy import deepcopy

from chatette.utils import choose


ENTITY_MARKER = "<<CHATETTE_ENTITY>>"
# HACK: prepends every entity (removed on output file writing)
#       to find back its index unambiguously.


class Example(object):
    """
    Represents an utterance (i.e. an example of sentence)
    that will later on be written in the output file(s).
    """
    def __init__(self, text="", entities=None):# -> None:
        super(Example, self).__init__()

        if entities is None:
            entities = []

        self.text = text
        self.entities = entities

    def __repr__(self):
        return "<'"+self.text+"' "+str(self.entities)+'>'

    def __hash__(self):
        return hash(self.text+str(self.entities))  # NOTE: those hashes seem inconsistent when testing whether an example was already generated (intent/definition.py:80)

    def __eq__(self, other):
        return self.__dict__ == other.__dict__
    def __ne__(self, other):
        return not self.__eq__(other)


def may_change_leading_case(text):
    """
    Checks whether the string `text` can
    change the letter case of its leading letter.
    """
    for c in text:
        if c.isalpha():
            return True
        if c.isspace():
            continue
        return False
    return False


def randomly_change_case(text):
    """
    Randomly set the case of the first letter of `text`.
    NOTE: this doesn't use `capitalize()` since we need to support changing the
          case of text that is already capitalized or indented.
    """
    if randint(0, 99) >= 50:
        return with_leading_lower(text)
    else:
        return with_leading_upper(text)


def with_leading_upper(text):
    """Returns `text` with a leading uppercase letter."""
    for (i, c) in enumerate(text):
        if not c.isspace():
            return text[:i] + text[i].upper() + text[(i + 1):]
    return text


def with_leading_lower(text):
    """Returns `text` with a leading lowercase letter."""
    for (i, c) in enumerate(text):
        if not c.isspace():
            return text[:i] + text[i].lower() + text[(i + 1):]
    return text


def may_get_leading_space(text):
    return (text != "" and not text.startswith(' '))  # TODO: Add '\t'?


class UnitDefinition(object):
    """Superclass representing a unit definition."""

    def __init__(self, name, rules=None, arg=None, casegen=False):
        if rules is None:
            rules = []

        self.type = "unit"

        self.name = name
        self.rules = rules  # list of list of `RulesContent`s => [[RulesContent]]

        self.argument_identifier = arg
        if arg is not None:
            PATTERN_ARG = r"(?<!\\)\$" + arg
            self.arg_regex = re.compile(PATTERN_ARG)
        else:
            self.arg_regex = None

        self.variations = dict()

        self.casegen = casegen  # IDEA: don't make the casegen variation agnostic
    
    def __repr__(self):
        result = self.type+":"+self.name
        if self.casegen:
            result = '&'+result
        return '<'+result+'>'

    def can_have_casegen(self):  # TODO: manage variations
        """
        Returns `True` if casegen may have an influence on
        any of the rules of this definition.
        """
        for rule in self.rules:
            if len(rule) > 0 and rule[0].can_have_casegen():
                return True
        return False

    def add_rule(self, rule, variation_name=None):
        # (RuleContent, str) -> ()
        self.rules.append(rule)
        if variation_name is not None:
            if variation_name == "":
                raise SyntaxError("Defining a " + self.type + " with an empty name" +
                                  "is not allowed")
            if variation_name not in self.variations:
                print("Creating var",variation_name,"in",self.type,self.name)
                self.variations[variation_name] = [rule]
                print("Variations:",self.variations)
                print("Rules:",self.rules)
            else:
                self.variations[variation_name].append(rule)

    def add_rules(self, rules, variation_name=None):
        # ([RuleContent], str) -> ()
        self.rules.extend(rules)
        if variation_name is not None:
            if variation_name == "":
                raise SyntaxError("Defining a " + self.type + " with an empty name" +
                                  "is not allowed")
            if variation_name not in self.variations:
                self.variations[variation_name] = rules
            else:
                self.variations[variation_name].extend(rules)

    def generate_random(self, variation_name=None, arg_value=None):
        """
        Generates one of your rule at random and
        returns the string generated and the entities inside it as a dict.
        """
        if variation_name is None:
            chosen_rule = choose(self.rules)
        else:
            if variation_name not in self.variations:
                raise SyntaxError("Couldn't find a variation named '" +
                                  variation_name + "' for " + self.type + " '" + self.name + "'")
            chosen_rule = choose(self.variations[variation_name])

        if chosen_rule is None:  # No rule
            return Example()

        example_text = ""
        example_entities = []
        generated_examples = dict()

        for token in chosen_rule:
            generated_token = token.generate_random(generated_examples)
            example_text += generated_token.text
            example_entities.extend(generated_token.entities)

        if self.casegen and self.can_have_casegen:
            example_text = randomly_change_case(example_text)

        # Replace `arg` inside the generated sentence
        if arg_value is not None and self.argument_identifier is not None:
            example_text = self.arg_regex.sub(arg_value, example_text)
            # pylint: disable=anomalous-backslash-in-string
            example_text = example_text.replace(r"\$", "$")

        return Example(example_text, example_entities)

    def generate_all(self, variation_name=None, arg_value=None):
        generated_examples = []

        relevant_rules = self.rules
        if variation_name is not None:
            print("variations:",self.variations)
            if variation_name in self.variations:
                relevant_rules = self.variations[variation_name]
            else:
                raise SyntaxError("Couldn't find variation '" +
                                  str(variation_name) + "' for " + str(self.type) +
                                  " '" + str(self.name) + "'")

        if not relevant_rules:  # No rules
            if variation_name is None:
                raise SyntaxError("No rules could be found for "+self.type+" '"+
                                self.name+"'")
            else:
                raise SyntaxError("No rules could be found for "+self.type+" '"+
                                self.name+"' (variation: '"+variation_name+"'")

        for rule in relevant_rules:
            examples_from_current_rule = []
            for sub_unit_rule in rule:
                sub_unit_possibilities = \
                    sub_unit_rule.generate_all()
                if len(examples_from_current_rule) <= 0:
                    examples_from_current_rule = sub_unit_possibilities
                else:
                    tmp_buffer = []
                    for ex in examples_from_current_rule:
                        for possibility in sub_unit_possibilities:
                            tmp_buffer.append(
                                Example(
                                    ex.text + possibility.text,
                                    ex.entities + possibility.entities
                                )
                            )
                    examples_from_current_rule = tmp_buffer
            generated_examples.extend(examples_from_current_rule)

        # Replace `arg` inside generated sentences
        if arg_value is not None and self.argument_identifier is not None:
            for (i, ex) in enumerate(generated_examples):
                ex.text = self.arg_regex.sub(arg_value, ex.text)
                # pylint: disable=anomalous-backslash-in-string
                generated_examples[i].text = ex.text.replace(r"\$", "$")

        # Apply casegen
        if self.casegen and self.can_have_casegen():
            tmp_examples = []
            for ex in generated_examples:
                (lower_ex, upper_ex) = (deepcopy(ex), deepcopy(ex))
                lower_ex.text = with_leading_lower(lower_ex.text)
                upper_ex.text = with_leading_upper(upper_ex.text)
                if lower_ex != upper_ex:
                    tmp_examples.append(lower_ex)
                    tmp_examples.append(upper_ex)
                else:
                    tmp_examples.append(ex)
            generated_examples = tmp_examples

        return generated_examples

    def get_max_nb_generated_examples(self, variation_name=None):
        """Returns the number of examples that can be generated by this token."""
        relevant_rules = self.rules
        if variation_name is not None:
            if variation_name in self.variations:
                relevant_rules = self.variations[variation_name]
            else:
                raise SyntaxError("Couldn't find variation '" + variation_name +
                                  "' for " + self.type + " '" + self.name + "'")

        nb_possible_ex = 0
        for rule in relevant_rules:
            rule_nb_ex = 0
            for sub_unit_rule in rule:
                current_nb_ex = sub_unit_rule.get_max_nb_generated_examples()
                if current_nb_ex is None:
                    continue
                if rule_nb_ex == 0:
                    rule_nb_ex = current_nb_ex
                else:
                    rule_nb_ex *= current_nb_ex
            nb_possible_ex += rule_nb_ex

        if self.casegen:
            nb_possible_ex *= 2
        return nb_possible_ex

    def print_DBG(self):
        print("\t" + self.type + ": " + self.name)
        print("\t\targument: " + str(self.argument_identifier))
        print("\t\tcasegen: " + str(self.casegen))
        print("\t\trules:")
        for rule in self.rules:
            print("\t\t\trule:")
            for content in rule:
                content.print_DBG(4)
        for variation in self.variations:
            print("\t\tvariation: " + variation)
            for rule in self.variations[variation]:
                print("\t\t\trule:")
                for content in rule:
                    content.print_DBG(3)
        print("")


class RuleContent(object):
    """
    Superclass represents anything that can be inside a rule:
    for words and word groups, it generates as is;
    for units, it is a link to a definition that can be generated.
    The rule also contains modifier used during the generation, such as:
        - leading-space: bool (a leading space will be added to the generated str)
        - casegen: bool (the first letter may be in upper- or lowercase)
        - randgen: str (if not `None` it might not be generated,
                        and if it is the same string than for another rule,
                        it will generate iff the other rule generated (and vice-versa))
        - percentgen: int (if `randgen` is enable, this is the percentage of
                           of chances that this rule will generate something)
        - arg: str (represents the identifier of an argument inside the rule,
                    which will be replaced by a value given upon generation)
        - variation-name: str (identifies which variation of the definition
                               we are calling)
    """

    def __init__(self, name, leading_space=False, variation_name=None,
                 arg_value=None, casegen=False, randgen=None, percentage_gen=50,
                 parser=None):
        if name is None or name == "":
            raise SyntaxError("Tried to create content without a contents (or a name)")
        self.name = name
        self.variation_name = variation_name
        self.arg_value = arg_value

        self.leading_space = leading_space

        self.casegen = casegen
        self.randgen = randgen
        if percentage_gen is not None:
            self.percentgen = int(percentage_gen)
        else:
            self.percentgen = 50

        self.parser = parser

    def can_have_casegen(self):
        """Returns `True` if casegen can have an influence on this rule."""
        return False

    def generate_random(self, generated_randgens=None):
        """
        Returns a string and its entities randomly generated from the rules the
        object represents. May return an empty string if `randgen` is enabled.
        `generated_randgens` is a dict of all the randgen names that have been
        decided as to generate or not, i.e. if "some randgen" is in
        `generated_randgens` and its value is `True`, all contents with this
        randgen must be generated; if its value is `False`, it cannot be
        generated; otherwise you can choose and put it into `generated_randgens`.
        """
        return Example()

    def generate_all(self):
        """
        Returns a list of all the strings and entities that can be generated
        from the rules this object represents. May include the empty string if
        it can be generated.
        """
        return [Example()]

    def get_max_nb_generated_examples(self):
        """Returns the number of examples that can be generated by this token."""
        pass

    def print_DBG(self, nb_indent=0):
        # (int) -> ()
        indentation = nb_indent * '\t'
        print(indentation + self.name)
        print(indentation + "\tvariation name: " + str(self.variation_name))
        print(indentation + "\targ value: " + str(self.arg_value))
        print(indentation + "\tcasegen: " + str(self.casegen))
        print(indentation + "\trandgen: " + str(self.randgen) + " with percentage: "
              + str(self.percentgen))

    def __repr__(self):
        result = "'"+self.name+"'"
        if self.casegen:
            result = '&'+result
        if self.leading_space:
            result = ' '+result
        if self.variation_name is not None:
            result += '#'+self.variation_name
        if self.randgen is not None:
            result += '?'+str(self.randgen)
            if self.percentgen != 50:
                result += '/'+str(self.percentgen)
        if self.arg_value is not None:
            result += '$'+self.arg_value
        return '<'+result+'>'
