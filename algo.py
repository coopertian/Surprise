from scipy.stats import rv_discrete
from scipy.spatial.distance import cosine
import numpy as np
import random as rd
import pickle
import time
import os

import common as cmn

class Algo:
    """Abstract Algo class where is defined the basic behaviour of a recomender
    algorithm"""
    def __init__(self, rm, ur, mr, movieBased=False, withDump=True, **kwargs):

        # whether the algo will be based on users
        # if the algo is user based, x denotes a user and y a movie
        # if the algo is movie based, x denotes a movie and y a user
        self.ub = not movieBased 

        if self.ub:
            self.rm = rm.T # we take the transpose of the rating matrix
            self.lastXi = cmn.lastUi
            self.lastYi = cmn.lastMi
            self.xr = ur
            self.yr = mr
        else:
            self.lastXi = cmn.lastMi
            self.lastYi = cmn.lastUi
            self.rm = rm
            self.xr = mr
            self.yr = ur

        self.est = 0 # set by the estimate method of the child class

        self.withDump = withDump
        self.infos = {}
        self.infos['name'] = 'undefined'
        self.infos['params'] = {} # dict of params specific to any algo
        self.infos['params']['Based on '] = 'users' if self.ub else 'movies'
        self.infos['ub'] = self.ub
        self.infos['preds'] = [] # list of predictions. see updatePreds
        self.infos['ur'] = ur # user ratings  dict
        self.infos['mr'] = mr # movie ratings dict
        self.infos['rm'] = self.rm  # rating matrix
        # Note: there is a lot of duplicated data, the dumped file will be
        # HUGE.



    def dumpInfos(self):
        if not self.withDump:
            return
        if not os.path.exists('./dumps'):
            os.makedirs('./dumps')
        
        date = time.strftime('%y%m%d-%Hh%Mm%S', time.localtime())
        name = ('dumps/' + date + '-' + self.infos['name'] + '-' +
            str(len(self.infos['preds'])))
        pickle.dump(self.infos, open(name,'wb'))

    def getx0y0(self, u0, m0):
        """return x0 and y0 based on the self.ub variable (see constructor)"""
        if self.ub:
            return u0, m0
        else:
            return m0, u0

    def updatePreds(self, u0, m0, r0, output=True):
        """update preds list and print some info if required
        
        should be called right after the estimate method
        """

        if output:
            if self.est == 0:
                print(cmn.Col.FAIL + 'Impossible to predict' + cmn.Col.ENDC)
            if self.est == r0:
                print(cmn.Col.OKGREEN + 'OK' + cmn.Col.ENDC)
            else:
                print(cmn.Col.FAIL + 'KO ' + cmn.Col.ENDC + str(self.est))

        # a prediction is a dict with the following keys
        # 'wasImpossible' : whether or not the prediction was possible
        # 'u0', 'm0', 'r0' (true rating) and 'est' (estimated rating)
        # '3tuples' (only if algo is analogy based). A list containing all the
        # 3-tuples used for estimation (structure content may depend on the algo)
        predInfo = {}
        if self.est == 0:
            self.est = 3 # default value
            predInfo['wasImpossible'] = True
        else:
            predInfo['wasImpossible'] = False

        predInfo['u0'] = u0 ; predInfo['m0'] = m0; predInfo['r0'] = r0
        predInfo['est'] = self.est
        if isinstance(self, AlgoUsingAnalogy):
            predInfo['3tuples'] = self.tuples
        self.infos['preds'].append(predInfo)

        
class AlgoRandom(Algo):
    """predict a random rating based on the distribution of the training set"""
    
    def __init__(self, rm, ur, mr):
        super().__init__(rm, ur, mr)
        self.infos['name'] = 'random'

        # estimation of the distribution
        fqs = [0, 0, 0, 0, 0]
        for x in range(1, self.lastXi):
            for y in range(1, self.lastYi):
                if self.rm[x, y] > 0:
                    fqs[self.rm[x, y] - 1] += 1
        fqs = [fq/sum(fqs) for fq in fqs]
        self.distrib = rv_discrete(values=([1, 2, 3, 4, 5], fqs))

    def estimate(self, u0, m0):
        self.est = self.distrib.rvs()

class AlgoUsingSim(Algo):
    """Abstract class for algos using a similarity measure
    sim parameter can be 'Cos' or 'MSD' for mean squared difference"""
    def __init__(self, rm, ur, mr, movieBased, sim, **kwargs):
        super().__init__(rm, ur, mr, movieBased, **kwargs)

        self.infos['params']['sim'] = sim
        self.constructSimMat(sim) # we'll need the similiarities

    def constructSimMat(self, sim):
        """construct the simlarity matrix"""
        if not(sim == 'Cos' or sim == 'MSD'):
            raise NameError('WrongSimName')

        # open or precalculate the similarity matrix if it does not exist yet
        simFileName = 'sim' + sim
        if self.ub:
            simFileName += 'Users'
        else:
            simFileName += 'Movies'
        print('Opening file', simFileName, '...')
        try:
            simFile = open(simFileName, 'rb')
            self.simMat = np.load(simFile)

        except IOError:
            print("File doesn't exist. Creating it...")
            self.simMat = np.empty((self.lastXi + 1, self.lastXi + 1))
            simMeasure = self.simCos if sim=='Cos' else self.simMSD
            for xi in range(1, self.lastXi + 1):
                for xj in range(xi, self.lastXi + 1):
                    self.simMat[xi, xj] = simMeasure(xi, xj)
                    self.simMat[xj, xi] = self.simMat[xi, xj]
            simFile = open(simFileName, 'wb')
            np.save(simFile, self.simMat)

    def simCos(self, xi, xj):
        """ return the similarity between two users or movies using cosine
        distance"""
        # movies rated by xi and xj or users having rated xi and xj
        Yij= [y for (y, _) in self.xr[xi] if self.rm[xj, y] > 0]

        if not Yij: # no common rating
            return 0

        # list of ratings of/by i and j
        iR = [self.rm[xi, y] for y in Yij]
        jR = [self.rm[xj, y] for y in Yij]

        return 1 - cosine(iR, jR)

    def simMSD(self, xi, xj):
        """ return the similarity between two users or movies using Mean
        Squared Difference"""
        # movies rated by xi andxj or users having rated xi and xj
        Yij = [y for (y, _) in self.xr[xi] if self.rm[xj, y] > 0]

        if not Yij:
            return 0

        # sum of squared differences:
        ssd = sum((self.rm[xi, y] - self.rm[xj, y])**2 for y in Yij)
        if ssd == 0:
            return  len(Yij) # maybe we should return more ?
        return len(Yij) / ssd


class AlgoBasicCollaborative(AlgoUsingSim):
    """Basic collaborative filtering algorithm"""

    def __init__(self, rm, ur, mr, movieBased=False, sim='Cos'):
        super().__init__(rm, ur, mr, movieBased=movieBased, sim=sim)

        self.k = 40

        self.infos['name'] = 'basicCollaborative'
        self.infos['params']['similarity measure'] = 'cosine'
        self.infos['params']['k'] = self.k

    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)
        # list of (x, sim(x0, x)) for u having rated m0 or for m rated by x0
        simX0 = [(x, self.simMat[x0, x]) for x in range(1, self.lastXi + 1) if
            self.rm[x, y0] > 0]

        # if there is nobody on which predict the rating...
        if not simX0:
            self.est = 0
            return

        # sort simX0 by similarity
        simX0 = sorted(simX0, key=lambda x:x[1], reverse=True)

        # let the KNN vote
        simNeighboors = [sim for (_, sim) in simX0[:self.k]]
        ratNeighboors = [self.rm[x, y0] for (x, _) in simX0[:self.k]]
        try:
            self.est = np.average(ratNeighboors, weights=simNeighboors)
        except ZeroDivisionError:
            self.est = 0

class AlgoUsingAnalogy(Algo):
    """Abstract class for algos that use an analogy framework"""
    def __init__(self, rm, ur, mr, movieBased=False):
        super().__init__(rm, ur, mr, movieBased)
        self.tuples = [] # list of 3-tuple (for the last prediction only)

    def isSolvable(self, ra, rb, rc):
        """return true if analogical equation is solvable else false"""
        return (ra == rb) or (ra == rc)

    def solve(self, ra, rb, rc):
        """ solve A*(a, b, c, x). Undefined if equation not solvable."""
        return rc - ra + rb

    def tvAStar (self, ra, rb, rc, rd):
        """return the truth value of A*(ra, rb, rc, rd)"""

        # map ratings into [0, 1]
        ra = (ra-1)/4.; rb = (rb-1)/4.; rc = (rc-1)/4.; rd = (rd-1)/4.; 
        return min(1 - abs(max(ra, rd) - max(rb, rc)), 1 - abs(min(ra, rd) -
            min(rb, rc)))

    def tvA(self, ra, rb, rc, rd):
        """return the truth value of A(ra, rb, rc, rd)"""

        # map ratings into [0, 1]
        ra = (ra-1)/4.; rb = (rb-1)/4.; rc = (rc-1)/4.; rd = (rd-1)/4.; 
        if (ra >= rb and rc >= rd) or (ra <= rb and rc <= rd):
            return 1 - abs((ra-rb) - (rc-rd))
        else:
            return 1 - max(abs(ra-rb), abs(rc-rd))


class AlgoGilles(AlgoUsingAnalogy):
    """geometrical analogy based recommender"""
    def __init__(self, rm, ur, mr, movieBased=False):
        super().__init__(rm, ur, mr, movieBased)
        self.infos['name'] = 'algoGilles'

    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)

        # if there are no ratings for y0, prediction is impossible
        if not self.yr[y0]:
            self.est = 0
            return

        candidates= [] # solutions to analogical equations
        self.tuples = [] # list of 3-tuples that are serve as candidates
        for i in range(1000):
            # randomly choose a, b, and c
            xa, ra = rd.choice(self.yr[y0])
            xb, rb = rd.choice(self.yr[y0])
            xc, rc = rd.choice(self.yr[y0])
            if xa != xb != xc and xa != xc and self.isSolvable(ra, rb, rc):
                # get info about the abcd 'paralellogram'
                (nYabc0, nrm) = self.getParall(xa, xb, xc, x0)
                if nrm < 1.5 * np.sqrt(nYabc0): # we allow some margin
                    sol = self.solve(ra, rb, rc)
                    candidates.append((sol, nrm, nYabc0))
                    self.tuples.append((xa, xb, xc, nYabc0, sol))

        # if there are candidates, estimate rating as a weighted average
        if candidates:
            ratings = [r for (r, _, _) in candidates]
            norms = [1/(nrm + 1) for (_, nrm, _) in candidates]
            nYs = [nY for (_, _, nY) in candidates]

            """
            self.est = int(round(np.average(ratings, weights=norms)))
            self.est = int(round(np.average(ratings, weights=nYs)))
            """
            self.est = np.average(ratings)
        else:
            self.est = 0


    def getParall(self, xa, xb, xc, x0):
        """return information about the parallelogram formed by xs: number of
        ratings in common and norm of the differences (see formula)"""

        # list of ys that xa, xb, xc, and x0 have commonly rated
        Yabc0 = [y for (y, _) in self.xr[xa] if (self.rm[xb, y] and self.rm[xc, y]
            and self.rm[x0, y])]

        # if there is no common rating
        if not Yabc0:
            return 0, float('inf')

        # lists of ratings for common ys
        xaRs = np.array([self.rm[xa, y] for y in Yabc0])
        xbRs = np.array([self.rm[xb, y] for y in Yabc0])
        xcRs = np.array([self.rm[xc, y] for y in Yabc0])
        x0Rs = np.array([self.rm[x0, y] for y in Yabc0])

        # the closer the norm to zero, the more abcd is in a paralellogram
        # shape
        nrm = np.linalg.norm((xaRs - xbRs) - (xcRs - x0Rs))

        return len(Yabc0), nrm

class AlgoPattern(AlgoUsingAnalogy):
    """analogy based recommender using patterns in 3-tuples"""
    def __init__(self, rm, ur, mr, movieBased=False):
        super().__init__(rm, ur, mr, movieBased)
        self.infos['name'] = 'algoPattern'

    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)

        # if there are no ratings for y0, prediction is impossible
        if not self.yr[y0]:
            self.est = 0
            return

        candidates= [] # solutions to analogical equations
        self.tuples = [] # list of 3-tuples that are serve as candidates
        tCat1 = np.var([1, 2, 1, 1]) #threshold of variance
        self.tuples = [] # list of 3-tuples that are serve as candidates
        for i in range(1000):
            # randomly choose a, b, and c
            xa, ra = rd.choice(self.yr[y0])
            xb, rb = rd.choice(self.yr[y0])
            xc, rc = rd.choice(self.yr[y0])
            # if pattern is a:a::b:x => swap b and c
            if ra == rb and ra != rc:
                xb, xc = xc, xb
                rb, rc = rc, rb

            cat1 = cat2 = cat3 = 0 # number of 3-tuples belonging to cat1, cat2...
            if xa != xb != xc and xa != xc and self.isSolvable(ra, rb, rc):
                Yabc0 = self.getYabc0(xa, xb, xc, x0)
                if not Yabc0:
                    break
                for y in Yabc0:
                    ray, rby, rcy, r0y = (self.rm[xa, y], self.rm[xb, y],
                        self.rm[xc, y], self.rm[x0, y])
                    # check if 3truple belongs to cat 1
                    # the variance check ensures that ratings are all equal, or
                    # only one differs from the othr with a diff of 1
                    if np.var([ray, rby, rcy, r0y]) <= tCat1:
                        cat1 += 1
                    # check if 3truple belongs to cat 2
                    elif (np.sign(ray-rby) == np.sign(rcy-r0y) and
                        min(abs(ray-rby), abs(rcy-r0y)) <= 2):
                        cat2 += 1

                    # check if 3truple belongs to cat 3
                    else:
                        cat3 += 1

                # Solution filtering depending on pattern
                if ra == rb == rc:
                    if cat1 >= cat2 + cat3:
                        candidates.append(ra)
                        self.tuples.append((xa, xb, xc, len(Yabc0),ra))
                elif abs(ra - rb) >= 2:
                    if cat2 > cat3:
                        candidates.append(rb)
                        self.tuples.append((xa, xb, xc, len(Yabc0),rb))
                else:
                    if cat1 >= cat2 + cat3 or cat2 > cat3:
                        candidates.append(rb)
                        self.tuples.append((xa, xb, xc, len(Yabc0),rb))

        # if there are candidates, estimate rating as a weighted average
        if candidates:
            ratings = [r for r in candidates]
            self.est = np.average(ratings)
        else:
            self.est = 0


    def getYabc0(self, xa, xb, xc, x0):
        # list of ys that xa, xb, xc, and x0 have commonly rated
        return [y for (y, _) in self.xr[xa] if (self.rm[xb, y] and self.rm[xc,
            y] and self.rm[x0, y])]




class AlgoWithBaseline(Algo):
    """Abstract class for algos that need a baseline"""
    def __init__(self, rm, ur, mr, movieBased, method, **kwargs):
        super().__init__(rm, ur, mr, movieBased, **kwargs)

        #compute users and items biases
        # see from 5.2.1 of RS handbook

        # mean of all ratings from training set
        self.mu = np.mean([r for l in self.rm for r in l if r > 0])

        self.xBiases = np.zeros(self.lastXi + 1)
        self.yBiases = np.zeros(self.lastYi + 1)

        print('Estimating biases...')
        if method == 'opt':
            # using stochastic gradient descent optimisation
            lambda4 = 0.02
            gamma = 0.005
            nIter = 20
            for i in range(nIter):
                for x, xRatings in self.xr.items():
                    for y, r in xRatings:
                        err = r - (self.mu + self.xBiases[x] + self.yBiases[y])
                        # update xBiases 
                        self.xBiases[x] += gamma * (err - lambda4 *
                            self.xBiases[x])
                        # udapte yBiases
                        self.yBiases[y] += gamma * (err - lambda4 *
                            self.yBiases[y])
        else:
            # using a more basic method 
            if self.ub:
                lambda2 = 10.
                lambda3 = 25.
            else:
                lambda2 = 25.
                lambda3 = 10.

            for x in range(1, self.lastXi + 1):
                # list of deviations from average for x
                devX = [r - self.mu for (_, r) in self.xr[x]]
                self.xBiases[x] = sum(devX) / (lambda2 + len(devX))
            for y in range(1, self.lastYi + 1):
                # list of deviations from average for y
                devY = [r - self.mu for (_, r) in self.yr[y]]
                self.yBiases[y] = sum(devY) / (lambda3 + len(devY))


    def getBaseline(self, x, y):
        return self.mu + self.xBiases[x] + self.yBiases[y]


class AlgoBaselineOnly(AlgoWithBaseline):
    """ Algo using only baseline""" 

    def __init__(self, rm, ur, mr, movieBased=False, method='opt'):
        super().__init__(rm, ur, mr, movieBased, method=method)
        self.infos['name'] = 'algoBaselineOnly'

    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)
        self.est = self.getBaseline(x0, y0)

class AlgoNeighborhoodWithBaseline(AlgoWithBaseline, AlgoUsingSim):
    """ Algo baseline AND deviation from baseline of the neighbors
        simlarity measure = cos"""
    def __init__(self, rm, ur, mr, movieBased=False, method='opt', sim='Cos'):
        super().__init__(rm, ur, mr, movieBased, method=method, sim=sim) 
        self.infos['name'] = 'neighborhoodWithBaseline'
        self.k = 40
        self.infos['params']['k'] = self.k

    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)
        self.est = self.getBaseline(x0, y0)


        simX0 = [(x, self.simMat[x0, x], r) for (x, r) in self.yr[y0]]

        # if there is nobody on which predict the rating...
        if not simX0:
            return # result will be just the baseline

        # sort simX0 by similarity
        simX0 = sorted(simX0, key=lambda x:x[1], reverse=True)

        # let the KNN vote
        k = self.k
        simNeighboors = [sim for (_, sim, _) in simX0[:k]]
        diffRatNeighboors = [r - self.getBaseline(x, y0) 
            for (x, _, r) in simX0[:k]]
        try:
            self.est += np.average(diffRatNeighboors, weights=simNeighboors)
        except ZeroDivisionError:
            return # just baseline

class AlgoKNNBelkor(AlgoWithBaseline):
    """ KNN learning interpolating weights from the training data. see 5.1.1
    from reco system handbook"""
    def __init__(self, rm, ur, mr, movieBased=False, method='opt'):
        super().__init__(rm, ur, mr, movieBased, method=method)
        self.weights = np.zeros((self.lastXi + 1, self.lastXi + 1),
        dtype='double')

        nIter = 20
        gamma = 0.005
        lambda10 = 0.002

        self.infos['name'] = 'KNNBellkor'

        for i in range(nIter):
            print("optimizing...", nIter - i, "iteration left")
            for x, xRatings in self.xr.items():
                for y, rxy in xRatings:
                    est = sum((r - self.getBaseline(x2, y)) *
                        self.weights[x, x2] for (x2, r) in self.yr[y])
                    est /= np.sqrt(len(self.yr[y]))
                    est += self.mu + self.xBiases[x] + self.yBiases[y]

                    err = rxy - est

                    # update x bias
                    self.xBiases[x] += gamma * (err - lambda10 *
                        self.xBiases[x])

                    # update y bias
                    self.yBiases[y] += gamma * (err - lambda10 *
                        self.yBiases[y])

                    # update weights
                    for x2, rx2y in self.yr[y]:
                        bx2y = self.getBaseline(x2, y)
                        wxx2 = self.weights[x, x2]
                        self.weights[x, x2] += gamma * ((err * (rx2y -
                            bx2y)/np.sqrt(len(self.yr[y]))) - (lambda10 * wxx2))


    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)
        
        self.est = sum((r - self.getBaseline(x2, y0)) *
            self.weights[x0, x2] for (x2, r) in self.yr[y0])
        self.est /= np.sqrt(len(self.yr[y0]))
        self.est += self.getBaseline(x0, y0)

        self.est = min(5, self.est)
        self.est = max(1, self.est)

class AlgoFactors(Algo):
    """Algo using latent factors. Implem heavily inspired by
    https://github.com/aaw/IncrementalSVD.jl"""
    def __init__(self, rm, ur, mr, movieBased=False):
        super().__init__(rm, ur, mr, movieBased)
        self.infos['name'] = 'algoLatentFactors'

        nFactors = 50 # number of factors
        nIter = 10
        self.px = np.ones((self.lastXi + 1, nFactors)) * 0.1 
        self.qy = np.ones((self.lastYi + 1, nFactors)) * 0.1
        residuals = []

        lambda4 = 0.02 # regularization extent
        gamma = 0.005 # learning rate

        self.infos['params']['nFactors'] = nFactors
        self.infos['params']['reguParam'] = lambda4
        self.infos['params']['learningRate'] = gamma
        self.infos['params']['nIter'] = nIter

        ratings = []
        for x, xRatings in self.xr.items():
            for y, val in xRatings:
                ratings.append(((x, y, val), [val, 0., 0.]))


        for f in range(nFactors):
            print(f)
            errors = [0., float('inf'), float('inf')]
            for i in range(nIter):
                for (x, y, val), (res) in ratings:
                    yF = self.qy[y, f] # value of feature f for y
                    xF = self.px[x, f] # value of feature f for x
                    res[1] = res[0] - yF * xF
                    errDiff = res[2] - res[1]
                    errors[0] += errDiff**2
                    res[2] = res[1]
                    self.qy[y, f] += gamma * (res[1] * xF - lambda4 * yF)
                    self.px[x, f] += gamma * (res[1] * yF - lambda4 * xF)
                errors = [0., errors[0], errors[1]]
            for _, (res) in ratings:
                res[0] = res[1]
                res[2] = 0.

        """
        for i in range(nIter):
            print(i)
            for f in range(nFactors):
                for x, xRatings in self.xr.items():
                    for y, r in xRatings:
                        err = r - np.dot(self.px[x, f], self.qy[y, f])
                        # update px 
                        self.px[x, f] += gamma * (err * self.qy[y, f] - lambda4 *
                            self.px[x, f])
                        # udapte qy
                        self.qy[y, f] += gamma * (err * self.px[x, f] - lambda4 *
                            self.qy[y, f])
        """

    def estimate(self, u0, m0):
        x0, y0 = self.getx0y0(u0, m0)
        
        self.est = np.dot(self.px[x0, :], self.qy[y0, :])

class AlgoGillesKnn(AlgoUsingSim,AlgoUsingAnalogy):
     """geometrical analogy based recommender using Knn to get analogical proportions instead of all the guys"""
     

     def __init__(self, rm, ur, mr, movieBased=False, sim='MSD'):
         super().__init__(rm, ur, mr, movieBased=movieBased, sim=sim)

         self.k = 40 #number of chosen neighbours

         self.infos['name'] = 'algoGillesKnn'
         self.infos['params']['k'] = self.k


     def estimate(self, u0, m0):
         x0, y0 = self.getx0y0(u0, m0)
         # list of (x, sim(x0, x)) for x having rated m0 or for m rated by x0
         simX0 = [(x, self.simMat[x0, x]) for x in range(1, self.lastXi + 1) if
             self.rm[x, y0] > 0]

         # if there is nobody to predict the rating, prediction is impossible (=0)
         if not simX0:
             self.est = 0
             return

         # sort simX0 by similarity decreasing order
         simX0 = sorted(simX0, key=lambda x:x[1], reverse=True)

         # get only the Knn guys
         fullList = [x for (x, _) in simX0]
         neighboorsList = [x for (x, _) in simX0[:self.k]]
         #simNeighboors = [sim for (_, sim) in simX0[:self.k]]
         #ratNeighboors = [self.rm[x, y0] for (x, _) in simX0[:self.k]]
                     
         
         candidates= []      # solutions to analogical equations
         #self.tuples = []    # list of 3-tuples that serve as candidates
         # choose a, b, and c among the neighbours here we get a cubic complexity wrt number of neighbours
         seen=[] #to avoid redundancy
         for xa in neighboorsList:
            for xb in neighboorsList:
                 for xc in neighboorsList:
                   if xa != xb != xc and xa != xc and self.isSolvable(self.rm[xa, y0], self.rm[xb, y0], self.rm[xc, y0]):
                 # get info about the abcd 'parallelogram'
                             (nrm,numberOfCommonMovies) = self.getParall(xa, xb, xc, x0)
                             if (nrm < 1.5 * np.sqrt(numberOfCommonMovies)): # we allow some margin
                                 sol = self.solve(self.rm[xa, y0], self.rm[xb, y0], self.rm[xc, y0])
                                 candidates.append((sol, nrm, numberOfCommonMovies))
                                 #seen.append(xa)
                                 #self.tuples.append((xa, xb, xc, nYabc0, sol))

         # if there are candidates, estimate rating as a weighted average
         if candidates:
             ratings = [sol for (sol, _, _) in candidates]
             #norms = [1/(nrm + 1) for (_, nrm, _) in candidates]
             #nYs = [nY for (_, _, nY) in candidates]
             self.est = np.average(ratings)
         else:
             self.est = 0
         print("candidates:",len(candidates),"estim=",self.est)
         
    
     def getParall(self, xa, xb, xc, x0):
         """return all information about the parallelogram formed by xs: number of
         ratings in common and norm of the difference (a-b)-(c-d) (see formula)"""

         # list of movies that xa, xb, xc, and x0 have commonly rated
         # or list of users having seen xa, xb, xc, and x0
         listOfCommon = [y for (y, _) in self.xr[xa] if (self.rm[xb, y] and self.rm[xc, y]
             and self.rm[x0, y])]
         #tv = [] # vector of componentwise truth value
         # if there is no common things
         if not listOfCommon:
             return float('inf'), 0

         # lists of ratings for common things y - 4 vectors with same dimension
         xaRs = np.array([self.rm[xa, y] for y in listOfCommon])
         xbRs = np.array([self.rm[xb, y] for y in listOfCommon])
         xcRs = np.array([self.rm[xc, y] for y in listOfCommon])
         x0Rs = np.array([self.rm[x0, y] for y in listOfCommon])

         # the closer the norm to zero, the more abcd looks like a parallelogram
         # norm is important
         nrm = np.linalg.norm((xaRs - xbRs) - (xcRs - x0Rs))
         
         # list of ratings from xa xb xc x0 for the common things
         #Yabc0 = [(self.rm[xa, y], self.rm[xb, y], self.rm[xc, y], self.rm[x0,y]) for y in listOfCommon]
         #compute the truth value componentwise
         #for (ra, rb, rc, rd) in Yabc0:
             #tv.append(self.tvAStar(ra, rb, rc, rd))
           #  tv.append(self.tvA(ra, rb, rc, rd))
             
         return nrm,  len(listOfCommon)
