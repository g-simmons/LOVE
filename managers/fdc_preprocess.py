"""
Authors:
    Jason Youn - jyoun@ucdavis.edu
    Simon Kit Sang, Chu - kschu@ucdavis.edu

Description:
    Preprocess manager for the FDC dataset.

To-do:
"""
# standard imports
import logging as log
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../'))

# third party imports
import gensim.utils as gensim_utils
from gensim.models.phrases import Phrases, Phraser
import gensim.parsing.preprocessing as gpp
import pandas as pd

# local imports
from utils.config_parser import ConfigParser


class FdcPreprocessManager:
    """
    Class for preprocessing the FDC data.
    """

    def __init__(self, config_filepath):
        """
        Class initializer.

        Inputs:
            config_filepath: (str) Configuration filepath.
        """
        self.configparser = ConfigParser(config_filepath)

    def _load_synonym_map(self, section='filter'):
        pd_map = pd.read_csv(
            self.configparser.getstr('synonym_map', section),
            sep='\t',
            index_col='from')

        return pd_map['to'].to_dict()

    def _map_synonyms(self, text, table):
        regex_str = '|'.join(r'\b%s\b' % re.escape(s) for s in table)
        return re.sub(regex_str, lambda x: table[x.group(0)], text)

    def _generate_custom_stopwords(self, section='filter'):
        """
        (Private) Generate custom stopwords by adding or removing
        user specified stopwords to the gensim's default stopwords.

        Inputs:
            section: (str, optional) Section name of the .ini file.

        Returns:
            (frozenset) New updated stopwords.
        """
        my_stopwords = list(gpp.STOPWORDS)

        # stopwords to add
        to_add_filename = self.configparser.getstr('stopwords_to_add', section)

        with open(to_add_filename, 'r') as file:
            to_add_list = file.read().splitlines()

        if len(to_add_list) > 0:
            log.info('Adding custom stopwords %s', to_add_list)
        else:
            log.info('Not adding any custom stopwords')

        # stopwords to remove
        to_remove_filename = self.configparser.getstr('stopwords_to_remove', section)

        with open(to_remove_filename, 'r') as file:
            to_remove_list = file.read().splitlines()

        if len(to_remove_list) > 0:
            log.info('Removing stopwords %s', to_remove_list)
        else:
            log.info('Not removing any custom stopword')

        # add and remove stopwords
        my_stopwords.extend(to_add_list)
        my_stopwords = [x for x in my_stopwords if x not in to_remove_list]

        return frozenset(my_stopwords)

    def _custom_remove_stopwords(self, s, stopwords):
        """
        (Private) Custom remove stopwords function.

        Inputs:
            s: (str) String to process.
            stopwords: (frozenset) Custom stopwords.

        Returns:
            (str) Preprocessed string with stopwords removed.
        """
        s = gensim_utils.to_unicode(s)
        return " ".join(w for w in s.split() if w not in stopwords)

    def _custom_lemmatize(self, text):
        result = gensim_utils.lemmatize(text)
        result = b' '.join(result).decode('utf-8')
        result = re.sub(r'/[^\s]+', '', result)

        return result

    def _build_custom_filter_list(self, section='filter'):
        """
        (Private) Build list of filters based on the configuration file
        that will be applied by gpp.preprocess_string().

        Inputs:
            section: (str, optional) Section name of the .ini file.

        Returns:
            custom_filters: (list) List of functions.
        """
        custom_filters = []

        if self.configparser.getbool('lower', section):
            log.debug('Converting to lower cases')
            custom_filters.append(lambda x: x.lower())

        if self.configparser.getbool('map_synonym', section):
            log.debug('Mapping synonym')
            map_table = self._load_synonym_map(section)
            custom_filters.append(lambda x: self._map_synonyms(x, map_table))

        if self.configparser.getbool('strip_punctuation', section):
            log.debug('Stripping punctuation')
            custom_filters.append(gpp.strip_punctuation)

        if self.configparser.getbool('strip_multiple_whitespaces', section):
            log.debug('Stripping multiple whitespaces')
            custom_filters.append(gpp.strip_multiple_whitespaces)

        if self.configparser.getbool('strip_numeric', section):
            log.debug('Stripping numeric')
            custom_filters.append(gpp.strip_numeric)

        if self.configparser.getbool('remove_stopwords', section):
            log.debug('Removing stopwords')
            stopwords = self._generate_custom_stopwords(section)
            custom_filters.append(lambda x: self._custom_remove_stopwords(x, stopwords))

        if self.configparser.getbool('strip_short', section):
            minsize = self.configparser.getint('strip_short_minsize', section)
            log.debug('Stripping words shorter than %d', minsize)
            custom_filters.append(lambda x: gpp.strip_short(x, minsize=minsize))

        if self.configparser.getbool('lemmatize', section):
            log.debug('Lemmatizing text')
            custom_filters.append(self._custom_lemmatize)

        return custom_filters

    def _generate_phrase(self, pd_data, load_model=False, section='phrase'):
        """
        (Private) Generate phrase using the gensim Phrase detection module.

        Inputs:
            pd_data: (pd.Series) Data which will be used to generate phase.
            section: (str, optional) Section name of the .ini file.

        Returns:
            pd_data: (pd.Series) Input data but using phrases.
        """
        if not self.configparser.getbool('generate_phrase', section):
            log.info('Skipping phrase generation...')
            return pd_data

        if load_model:
            model_filepath = self.configparser.getstr('phrase_model', section)
            model = Phraser.load(model_filepath)

            # apply phrase model
            log.info('Applying loaded phrase model...')
            pd_data = pd_data.apply(
                lambda x: model[x],
                convert_dtype=False)
        else:
            log.info('Generating new phrases...')

            # this is our training data
            sentences = pd_data.tolist()

            # detect phrases using the configuration
            model = Phrases(
                sentences,
                min_count=self.configparser.getint('min_count', section),
                threshold=self.configparser.getfloat('threshold', section),
                max_vocab_size=self.configparser.getint('max_vocab_size', section),
                progress_per=self.configparser.getint('progress_per', section),
                scoring=self.configparser.getstr('scoring', section))

            # apply trained model to generate phrase
            log.info('Applying phrase model...')
            pd_data = pd_data.apply(
                lambda x: model[x],
                convert_dtype=False)

            # save phrase model
            model_filepath = self.configparser.getstr('phrase_model', section)

            log.info('Saving phrase model to \'%s\'...', model_filepath)
            model.save(model_filepath)

            # dump phrase and its score as text
            phrase_score_list = []
            for phrase, score in model.export_phrases(sentences):
                phrase_score_list.append([phrase.decode('utf-8'), score])

            pd_phrase_score = pd.DataFrame(phrase_score_list, columns=['phrase', 'score'])
            pd_phrase_score.drop_duplicates(subset='phrase', inplace=True)

            export_filepath = self.configparser.getstr('phrase_dump_filename', section)

            log.info('Dumping phrases to \'%s\'...', export_filepath)
            pd_phrase_score.to_csv(export_filepath, sep='\t', index=False)

        return pd_data

    def preprocess_column(self, pd_data, load_model=False):
        """
        Preprocess specified column.

        Inputs:
            pd_data: (pd.Series) Input data to preprocess.

        Returns:
            pd_data: (pd.Series) Preprocess data.
        """
        # preprocess using set of filters
        custom_filters = self._build_custom_filter_list()

        log.info('Applying preprocess filters to the %s...', pd_data.name)
        pd_data = pd_data.apply(
            lambda x: gpp.preprocess_string(x, custom_filters),
            convert_dtype=False)

        # generate phrase based on the configuration
        pd_data = self._generate_phrase(pd_data, load_model=load_model)

        # join the list of words into space delimited string
        pd_data = pd_data.apply(lambda x: ' '.join(x))

        return pd_data

    def get_vocabs(self, pd_data):
        log.info('Getting all vocabs...')

        vocabs = []
        for row in pd_data.tolist():
            vocabs.extend(row.split(' '))

        vocabs = list(set(vocabs))
        vocabs = sorted(vocabs, key=str.lower)

        log.info('Got %d unique vocabularies', len(vocabs))

        return vocabs
